"""
pipeline_query.py — Query Pipeline
-------------------------------------
Orchestrates the retrieval flow:
  1. Embed the user query (embendding_service)
  2. Hybrid search in OpenSearch — BM25 + kNN
  3. Rerank top-K candidates
  4. Return top-N results with chunk metadata (document_id, page, bbox, text)
  5. Fetch original document bytes from Ceph bucket 'docs'

Chunk metadata traceback
-------------------------
When resolving chunk metadata (page, bbox, block_ids) for a hit:
  1. Try Ceph bucket 'chunks'  (authoritative, always up-to-date)
  2. Fall back to local  app/chunk_tmp/{doc_id}_chunks.json  (dev / offline)

Side-effect:
  After embedding the query the raw vector is recorded in embedding_viz.py
  so the visualization page can show it in the 3D embedding space.
"""

from __future__ import annotations

import json
import logging
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolve sibling service directories
# ---------------------------------------------------------------------------

_APP_DIR      = Path(__file__).parent.resolve()
_PROJECT_ROOT = _APP_DIR.parent.resolve()

_STORAGE_DIR = _PROJECT_ROOT / "storage_service"
_EMBED_DIR   = _PROJECT_ROOT / "embendding_service"
_CHUNK_DIR_P = _APP_DIR / "chunk_tmp"

for _p in [str(_STORAGE_DIR), str(_EMBED_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Direct imports
# ---------------------------------------------------------------------------

from object import get_file_stream                # storage_service
from embedder import search as embed_search       # embendding_service
from reranker import rerank, candidates_from_hits # embendding_service

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUCKET_DOCS   = "docs"
BUCKET_CHUNKS = "chunks"
DEFAULT_TOP_K = 50
DEFAULT_TOP_N = 5


# ===========================================================================
# Steps 1–4 — Query → Embed → Search → Rerank → Results
# ===========================================================================

def run_query(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    top_n: int = DEFAULT_TOP_N,
) -> list[dict[str, Any]]:
    """
    Run the full retrieval pipeline for a user query.

    Returns
    -------
    List of dicts (length ≤ top_n):
        {
            "rank":        int,
            "chunk_id":    str,
            "document_id": str,
            "page":        int,
            "bbox":        [x0, y0, x1, y1],
            "text":        str,
        }
    """
    if not query.strip():
        return []

    # Side-effect: record query embedding for 3D visualization
    try:
        from embedding_viz import record_query_embedding  # noqa: PLC0415
        record_query_embedding(query)
    except Exception as exc:
        logger.debug("viz record_query_embedding skipped: %s", exc)

    logger.info("Hybrid search: %r", query[:80])
    hits = embed_search(query=query, top_k=top_k)

    if not hits:
        return []

    logger.info("Reranking %d candidates → top %d", len(hits), top_n)
    candidates = candidates_from_hits(hits)
    ranked     = rerank(query, candidates, top_n=top_n)

    results = []
    for r in ranked:
        meta = _resolve_chunk_meta(r.chunk_id)
        results.append({
            "rank":        r.rank,
            "chunk_id":    r.chunk_id,
            "document_id": meta.get("document_id", _doc_id_from_chunk_id(r.chunk_id)),
            "page":        meta.get("page", 1),
            "bbox":        meta.get("bbox", []),
            "text":        r.text,
        })

    return results


# ===========================================================================
# Step 5 — Fetch original document bytes from Ceph 'docs'
# ===========================================================================

def fetch_document(document_id: str) -> tuple[BytesIO | None, str]:
    """
    Retrieve original file bytes from Ceph bucket 'docs'.
    Returns (stream, object_name).  stream is None if not found.
    """
    for ext in [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"]:
        object_name = f"{document_id}{ext}"
        stream = get_file_stream(BUCKET_DOCS, object_name)
        if stream is not None:
            logger.info("Found document in Ceph: %s", object_name)
            return stream, object_name

    logger.warning("Document not found in Ceph: %s", document_id)
    return None, ""


# ===========================================================================
# Internal helpers
# ===========================================================================

def _resolve_chunk_meta(chunk_id: str) -> dict:
    """
    Resolve page, bbox, etc. for a chunk_id.

    Priority
    --------
    1. Ceph bucket 'chunks'                  — authoritative
    2. Local  app/chunk_tmp/{doc_id}.json    — dev / offline fallback
    """
    doc_id = _doc_id_from_chunk_id(chunk_id)

    # 1. Try Ceph first
    ceph_chunks = _load_chunks_from_ceph(doc_id)
    if ceph_chunks is not None:
        for chunk in ceph_chunks:
            if chunk.get("chunk_id") == chunk_id:
                return chunk

    # 2. Fall back to local file
    chunk_file = _CHUNK_DIR_P / f"{doc_id}_chunks.json"
    if chunk_file.exists():
        try:
            with chunk_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for chunk in data.get("chunks", []):
                if chunk.get("chunk_id") == chunk_id:
                    return chunk
        except Exception as exc:
            logger.warning("Local chunk read error %s: %s", chunk_file, exc)

    return {}


def _load_chunks_from_ceph(doc_id: str) -> list[dict] | None:
    """
    Download chunk JSON from Ceph bucket 'chunks'.
    Returns chunk list, or None on any failure.
    """
    object_name = f"{doc_id}_chunks.json"
    try:
        stream = get_file_stream(BUCKET_CHUNKS, object_name)
        if stream is None:
            return None
        data = json.load(stream)
        return data.get("chunks", []) if isinstance(data, dict) else data
    except Exception as exc:
        logger.debug("Ceph chunk load failed for %s: %s", object_name, exc)
        return None


def _doc_id_from_chunk_id(chunk_id: str) -> str:
    """
    Derive document_id from chunk_id.
    Format: <document_id>_p<page>_c<index>
    Example: 'invoice_abc12345_p2_c3' → 'invoice_abc12345'
    """
    parts = chunk_id.rsplit("_p", 1)
    return parts[0] if len(parts) == 2 else chunk_id