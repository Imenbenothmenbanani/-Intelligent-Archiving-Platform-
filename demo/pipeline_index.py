"""
pipeline_index.py — Indexation Pipeline
-----------------------------------------
Orchestrates the full document indexation flow:
  1. Upload file to Ceph bucket 'docs' via storage_service
  2. Run OCR via ocr_service (subprocess — Python 3.10 isolated env)
     OCR pipeline options are passed from the caller (selected in the UI).
  3. Return OCR JSON to caller for human-in-the-loop correction
  4. Accept corrected OCR JSON, run chunk_service
  5. Save chunks JSON to Ceph bucket 'chunks'          ← NEW
  6. Embed chunks and index into OpenSearch via embendding_service
  7. Side-effect: record chunk embeddings for visualization

Ceph buckets
------------
  docs   — original uploaded documents
  chunks — chunk JSON files (one per document, key = {document_id}_chunks.json)

Python version note
-------------------
- ocr_service requires Python 3.10.11 and runs in its own Poetry env.
  It is invoked via subprocess so there is zero import-level conflict.
- chunk_service (3.11) and embendding_service (3.11) are imported directly.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolve sibling service directories
# ---------------------------------------------------------------------------

_APP_DIR      = Path(__file__).parent.resolve()
_PROJECT_ROOT = _APP_DIR.parent.resolve()

_STORAGE_DIR = _PROJECT_ROOT / "storage_service"
_CHUNK_DIR   = _PROJECT_ROOT / "chunk_service"
_EMBED_DIR   = _PROJECT_ROOT / "embendding_service"
_OCR_DIR     = _PROJECT_ROOT / "ocr_service"

for _p in [str(_STORAGE_DIR), str(_CHUNK_DIR), str(_EMBED_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Direct imports (Python 3.11+ services)
# ---------------------------------------------------------------------------

from bucket import create_bucket        # storage_service
from object import upload_file          # storage_service
from object import get_file_stream      # storage_service — chunk retrieval
from chunk_builder import build_chunks  # chunk_service
from embedder import index_chunks       # embendding_service

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUCKET_DOCS   = "docs"
BUCKET_CHUNKS = "chunks"

OCR_OUTPUT_DIR = _APP_DIR / "ocr_tmp"
CHUNK_DIR_OUT  = _APP_DIR / "chunk_tmp"

OCR_OUTPUT_DIR.mkdir(exist_ok=True)
CHUNK_DIR_OUT.mkdir(exist_ok=True)

# Default OCR options — mirrors what the UI checkboxes default to
DEFAULT_OCR_OPTIONS: dict[str, bool] = {
    "use_doc_orientation_classify": True,
    "use_doc_unwarping":            True,
    "use_layout_detection":         True,
    "use_ocr_for_image_block":      False,
    "format_block_content":         True,
    "merge_layout_blocks":          False,
}


# ===========================================================================
# Step 1 + 2 — Upload to Ceph → OCR → return JSON for review
# ===========================================================================

def upload_and_ocr(
    file_bytes:  bytes,
    filename:    str,
    ocr_options: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """
    Save *file_bytes* to Ceph bucket 'docs', then run OCR via subprocess
    (ocr_service's own Poetry 3.10 venv) with the caller-supplied options.

    Parameters
    ----------
    file_bytes  : raw document bytes
    filename    : original filename
    ocr_options : PaddleOCR-VL boolean flags chosen in the UI.
                  Merged over DEFAULT_OCR_OPTIONS.

    Returns
    -------
    {
        "document_id": str,
        "object_name": str,
        "ocr_json":    dict,
        "ocr_options": dict,
    }
    """
    opts = {**DEFAULT_OCR_OPTIONS, **(ocr_options or {})}

    # Ensure buckets exist
    for bucket in (BUCKET_DOCS, BUCKET_CHUNKS):
        try:
            create_bucket(bucket)
        except Exception:
            pass

    # Build collision-free document_id
    stem        = Path(filename).stem
    suffix      = Path(filename).suffix.lower()
    document_id = f"{stem}_{uuid.uuid4().hex[:8]}"
    object_name = f"{document_id}{suffix}"

    # Upload document to Ceph
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        logger.info("Ceph upload (docs): %s", upload_file(BUCKET_DOCS, tmp_path, object_name))
    finally:
        os.unlink(tmp_path)

    # Run OCR subprocess
    ocr_out_dir = OCR_OUTPUT_DIR / document_id
    ocr_out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        ocr_input_path = tmp.name
    try:
        ocr_json = _run_ocr_subprocess(ocr_input_path, str(ocr_out_dir), opts)
    finally:
        os.unlink(ocr_input_path)

    return {
        "document_id": document_id,
        "object_name": object_name,
        "ocr_json":    ocr_json,
        "ocr_options": opts,
    }


def _run_ocr_subprocess(input_path: str, output_dir: str, opts: dict[str, bool]) -> dict:
    """
    Invoke ocr_service/main.py via its dedicated venv, forwarding option flags
    as CLI arguments.

    CLI flag mapping (main.py must accept these — see ocr_service/main.py):
        use_doc_orientation_classify → --orientation
        use_doc_unwarping            → --unwarp
        use_layout_detection         → --layout
        use_ocr_for_image_block      → --ocr-images
        format_block_content         → --format
        merge_layout_blocks          → --merge-layout
    """
    ocr_python = _OCR_DIR / ".venv" / "Scripts" / "python.exe"
    if not ocr_python.exists():
        ocr_python = _OCR_DIR / ".venv" / "bin" / "python"
    if not ocr_python.exists():
        raise RuntimeError(
            f"OCR venv not found at {ocr_python}. "
            f"Run 'cd {_OCR_DIR} && poetry install'."
        )

    cmd = [str(ocr_python), "main.py", "--input", input_path, "--output", output_dir]

    flag_map = {
        "use_doc_orientation_classify": "--orientation",
        "use_doc_unwarping":            "--unwarp",
        "use_layout_detection":         "--layout",
        "use_ocr_for_image_block":      "--ocr-images",
        "format_block_content":         "--format",
        "merge_layout_blocks":          "--merge-layout",
    }
    for key, cli_flag in flag_map.items():
        if opts.get(key, False):
            cmd.append(cli_flag)

    logger.info("OCR cmd: %s", " ".join(cmd))
    t0 = time.perf_counter()

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.run(
        cmd, cwd=str(_OCR_DIR), capture_output=True, text=True, timeout=600, env=env
    )

    logger.info("OCR done in %.1fs  rc=%d", time.perf_counter() - t0, proc.returncode)

    if proc.returncode != 0:
        logger.error("OCR stderr:\n%s", proc.stderr)
        raise RuntimeError(
            f"OCR subprocess failed (exit {proc.returncode}):\n{proc.stderr[-800:]}"
        )

    stem      = Path(input_path).stem
    json_path = Path(output_dir) / stem / "result.json"
    if not json_path.exists():
        candidates = list(Path(output_dir).rglob("*.json"))
        if not candidates:
            raise RuntimeError(f"No JSON output under {output_dir}")
        json_path = candidates[0]
        logger.warning("Fallback JSON: %s", json_path)

    with json_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ===========================================================================
# Step 4–6 — Corrected JSON → Chunk → Ceph → Embed + Index
# ===========================================================================

def confirm_and_index(
    document_id:    str,
    corrected_json: dict,
) -> dict[str, Any]:
    """
    Chunk, save to Ceph bucket 'chunks', embed, index into OpenSearch.

    Returns
    -------
    {
        "document_id":    str,
        "chunks_indexed": int,
        "chunks_object":  str,
    }
    """
    # ── Chunk ─────────────────────────────────────────────────────────
    logger.info("Chunking: %s", document_id)
    build_chunks(
        ocr_json      = corrected_json,
        document_id   = document_id,
        max_tokens    = 500,
        min_tokens    = 150,
        overlap_ratio = 0.2,
        dry_run       = False,
        output_dir    = str(CHUNK_DIR_OUT),
    )

    chunk_file        = CHUNK_DIR_OUT / f"{document_id}_chunks.json"
    chunk_object_name = f"{document_id}_chunks.json"
    logger.info("Chunks → %s", chunk_file)

    # ── Save chunks JSON to Ceph bucket 'chunks' ───────────────────────
    try:
        msg = upload_file(BUCKET_CHUNKS, str(chunk_file), chunk_object_name)
        logger.info("Ceph upload (chunks): %s", msg)
    except Exception as exc:
        logger.warning("Could not upload chunks to Ceph (non-fatal): %s", exc)

    # ── Embed + index into OpenSearch ─────────────────────────────────
    logger.info("Embedding & indexing: %s", document_id)
    indexed_docs   = index_chunks(str(chunk_file), upload=True)
    chunks_indexed = len(indexed_docs)
    logger.info("Indexed %d chunks", chunks_indexed)

    # ── Side-effect: record for 3D visualization ───────────────────────
    try:
        from embedding_viz import record_chunk_embeddings  # noqa: PLC0415
        record_chunk_embeddings(chunk_file)
    except Exception as exc:
        logger.debug("viz hook skipped: %s", exc)

    return {
        "document_id":    document_id,
        "chunks_indexed": chunks_indexed,
        "chunks_object":  chunk_object_name,
    }


# ===========================================================================
# Chunk retrieval from Ceph — used by pipeline_query for traceback
# ===========================================================================

def fetch_chunks_from_ceph(document_id: str) -> list[dict] | None:
    """
    Download chunk JSON from Ceph bucket 'chunks' for *document_id*.
    Returns chunk list, or None if not found (caller falls back to local).
    """
    object_name = f"{document_id}_chunks.json"
    stream = get_file_stream(BUCKET_CHUNKS, object_name)
    if stream is None:
        logger.warning("Chunk not in Ceph: %s", object_name)
        return None
    try:
        data   = json.load(stream)
        chunks = data.get("chunks", []) if isinstance(data, dict) else data
        logger.info("Loaded %d chunks from Ceph for %s", len(chunks), document_id)
        return chunks
    except Exception as exc:
        logger.warning("Ceph chunk parse error %s: %s", object_name, exc)
        return None