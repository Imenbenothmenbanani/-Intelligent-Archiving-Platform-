"""
main.py — FastAPI application
------------------------------
Endpoints
---------
POST  /api/index/upload         Upload + OCR (with UI-selected pipeline options)
POST  /api/index/confirm        Chunk → Ceph → Embed → Index
POST  /api/query                Query → top-N results
GET   /api/document/{doc_id}    Stream original file from Ceph
GET   /api/viz/points           3D embedding visualization data
DELETE /api/viz/clear           Clear visualization store
GET   /                         HTML interface

Run
---
    poetry run uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline_index import upload_and_ocr, confirm_and_index
from pipeline_query import fetch_document, run_query
from embedding_viz import router as viz_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Intelligent Archiving Platform",
    description="OCR → Chunk → Embed pipeline with hybrid semantic search",
    version="1.1.0",
)

app.include_router(viz_router)

_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ===========================================================================
# HTML
# ===========================================================================

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    index_file = _STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found in static/")
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


# ===========================================================================
# Indexation endpoints
# ===========================================================================

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


@app.post("/api/index/upload")
async def index_upload(
    file:        UploadFile  = File(...),
    ocr_options: Optional[str] = Form(default=None),
) -> dict[str, Any]:
    """
    Step 1–2: Receive document + OCR option flags (JSON string from the form),
    save to Ceph, run OCR subprocess.

    ocr_options (form field, JSON string):
        {
            "use_doc_orientation_classify": bool,
            "use_doc_unwarping":            bool,
            "use_layout_detection":         bool,
            "use_ocr_for_image_block":      bool,
            "format_block_content":         bool,
            "merge_layout_blocks":          bool
        }

    Returns { document_id, object_name, ocr_json, ocr_options }.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    # Parse OCR options JSON if supplied
    opts: dict[str, bool] | None = None
    if ocr_options:
        try:
            opts = json.loads(ocr_options)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="ocr_options must be valid JSON.")

    logger.info("Upload: %s  (%d bytes)  opts=%s", file.filename, len(file_bytes), opts)

    try:
        result = upload_and_ocr(
            file_bytes  = file_bytes,
            filename    = file.filename or "document",
            ocr_options = opts,
        )
    except RuntimeError as exc:
        logger.error("upload_and_ocr failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in upload_and_ocr")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}")

    return result


class ConfirmRequest(BaseModel):
    document_id: str
    ocr_json:    dict


@app.post("/api/index/confirm")
async def index_confirm(body: ConfirmRequest) -> dict[str, Any]:
    """
    Step 4–6: Chunk → save to Ceph 'chunks' → embed → index OpenSearch.
    Returns { document_id, chunks_indexed, chunks_object }.
    """
    if not body.document_id:
        raise HTTPException(status_code=422, detail="document_id is required.")
    if not body.ocr_json:
        raise HTTPException(status_code=422, detail="ocr_json is required.")

    logger.info("Confirm & index: %s", body.document_id)

    try:
        result = confirm_and_index(
            document_id    = body.document_id,
            corrected_json = body.ocr_json,
        )
    except Exception as exc:
        logger.exception("confirm_and_index failed")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}")

    return result


# ===========================================================================
# Query endpoint
# ===========================================================================

class QueryRequest(BaseModel):
    query: str
    top_n: int = 5


@app.post("/api/query")
async def query(body: QueryRequest) -> dict[str, Any]:
    if not body.query.strip():
        raise HTTPException(status_code=422, detail="Query cannot be empty.")

    top_n = max(1, min(body.top_n, 20))
    logger.info("Query: %r  top_n=%d", body.query[:80], top_n)

    try:
        results = run_query(query=body.query, top_n=top_n)
    except Exception as exc:
        logger.exception("run_query failed")
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")

    return {"results": results}


# ===========================================================================
# Document fetch endpoint
# ===========================================================================

_MIME: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".tif":  "image/tiff",
    ".tiff": "image/tiff",
}


@app.get("/api/document/{document_id}")
async def get_document(document_id: str):
    logger.info("Document fetch: %s", document_id)

    try:
        stream, object_name = fetch_document(document_id)
    except Exception as exc:
        logger.exception("fetch_document failed for %s", document_id)
        raise HTTPException(status_code=500, detail=f"Could not fetch document: {exc}")

    if stream is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_id}' not found in Ceph.",
        )

    suffix     = Path(object_name).suffix.lower()
    media_type = _MIME.get(suffix, "application/octet-stream")
    file_bytes = stream.read()

    return StreamingResponse(
        iter([file_bytes]),
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{object_name}"',
            "Content-Length":      str(len(file_bytes)),
        },
    )