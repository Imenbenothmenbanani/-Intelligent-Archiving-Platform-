"""
embedding_viz.py — Embedding Visualization Pipeline
-----------------------------------------------------
Captures every query/chunk embedding and reduces them to 3D for display.

Key improvements
------------------------------------
1. Dimensionality reduction: UMAP(3) with tight clustering
   UMAP preserves both local and global neighbourhood structure better than t-SNE,
   causing semantically similar chunks to form tight, distinct clusters.
   Uses min_dist=0.05 (lower = tighter clusters) and cosine distance metric,
   ideal for LLM text embeddings. Coordinates scaled to [-0.8, 0.8] to keep
   clusters concentrated in the visualization viewport.

2. Query TTL: query embeddings carry a 'ttl_seconds' field (default 120 s).
   The /api/viz/points endpoint filters out expired queries so the frontend
   only ever shows a query dot briefly after it was issued.

3. Document coloring: each unique doc_id gets a stable colour index so the
   frontend can colour chunk spheres by document — mirrors category colours
   in UMAP plots.

4. Cluster centroid: the response includes per-doc centroids so the frontend
   can show a label floating above each document cluster.

Endpoints (registered in main.py via router)
--------------------------------------------
    GET    /api/viz/points     All stored chunks + active queries, reduced to 3D
    GET    /api/viz/status     Quick count without reduction (no GPU)
    DELETE /api/viz/clear      Wipe the store

Side-effect hooks (called from pipelines)
------------------------------------------
    record_query_embedding(query)       — pipeline_query.run_query()
    record_chunk_embeddings(chunk_file) — pipeline_index.confirm_and_index()
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolve sibling service directories
# ---------------------------------------------------------------------------

_APP_DIR      = Path(__file__).parent.resolve()
_PROJECT_ROOT = _APP_DIR.parent.resolve()
_EMBED_DIR    = _PROJECT_ROOT / "embendding_service"

if str(_EMBED_DIR) not in sys.path:
    sys.path.insert(0, str(_EMBED_DIR))

# Lazy embedder import (avoids loading model at startup)
_embed_query_fn   = None
_encode_fn        = None
_load_chunks_fn   = None
_DEFAULT_INSTRUCT = None


def _import_embedder():
    global _embed_query_fn, _encode_fn, _load_chunks_fn, _DEFAULT_INSTRUCT
    if _embed_query_fn is None:
        from embedder import (                      # noqa: PLC0415
            embed_query        as _eq,
            _encode            as _enc,
            load_chunks        as _lc,
            DEFAULT_INDEX_INSTRUCT as _di,
        )
        _embed_query_fn   = _eq
        _encode_fn        = _enc
        _load_chunks_fn   = _lc
        _DEFAULT_INSTRUCT = _di


# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------

VIZ_STORE      = _APP_DIR / "viz_store.json"
QUERY_TTL_SECS = 120   # queries older than this are hidden from the viz


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_store() -> list[dict]:
    if not VIZ_STORE.exists():
        return []
    try:
        with VIZ_STORE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("viz_store read error: %s", exc)
        return []


def _save_store(records: list[dict]) -> None:
    tmp = VIZ_STORE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    tmp.replace(VIZ_STORE)


def _append_record(record: dict) -> None:
    records = _load_store()
    record.setdefault("timestamp", _now_iso())
    records.append(record)
    _save_store(records)


def _is_query_alive(record: dict) -> bool:
    """Return True if this query record is still within its TTL window."""
    ts = record.get("timestamp")
    if not ts:
        return False
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
        return age <= QUERY_TTL_SECS
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public side-effect hooks
# ---------------------------------------------------------------------------

def record_query_embedding(query: str) -> None:
    """Embed query and persist with TTL. Non-fatal."""
    try:
        _import_embedder()
        vec = _embed_query_fn(query)
        _append_record({
            "id":          f"q_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "label":       query[:80],
            "kind":        "query",
            "doc_id":      "",
            "vector":      vec.tolist(),
            "ttl_seconds": QUERY_TTL_SECS,
        })
        logger.info("Recorded query embedding: %r", query[:40])
    except Exception as exc:
        logger.warning("record_query_embedding failed (non-fatal): %s", exc)


def record_chunk_embeddings(chunk_file: str | Path) -> None:
    """Embed every chunk in chunk_file and persist. Non-fatal."""
    try:
        _import_embedder()
        chunks  = _load_chunks_fn(chunk_file)
        texts   = [c["text"] for c in chunks]
        vectors = _encode_fn(texts, instruct=_DEFAULT_INSTRUCT)

        records = _load_store()
        for chunk, vec in zip(chunks, vectors):
            records.append({
                "id":        chunk["chunk_id"],
                "label":     chunk["text"][:80],
                "kind":      "chunk",
                "doc_id":    chunk.get("document_id", ""),
                "page":      chunk.get("page", 1),
                "vector":    vec.tolist(),
                "timestamp": _now_iso(),
            })
        _save_store(records)
        logger.info("Recorded %d chunk embeddings", len(chunks))
    except Exception as exc:
        logger.warning("record_chunk_embeddings failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Dimensionality reduction  —  UMAP(3)
# ---------------------------------------------------------------------------

def _reduce_to_3d(matrix: np.ndarray) -> np.ndarray:
    """
    Reduce N×D to N×3 preserving cluster structure using UMAP.
    
    Returns float32 array, axes normalised to roughly [-1, 1].
    """
    n, d = matrix.shape

    if n == 1:
        return np.zeros((1, 3), dtype=np.float32)

    if n < 4:
        # Fallback for very small datasets (UMAP needs >= 4 points for 3D reliably)
        from sklearn.decomposition import PCA as _PCA
        pca_dims = min(3, n)
        pca_out = _PCA(n_components=pca_dims, random_state=42).fit_transform(matrix)
        if pca_out.shape[1] < 3:
            pad = np.zeros((n, 3 - pca_out.shape[1]), dtype=np.float32)
            coords = np.hstack([pca_out, pad])
        else:
            coords = pca_out
        coords = coords.astype(np.float32)
    else:
        # ── UMAP ────────────────────────────────────────────────────
        import umap
        
        # Dynamically scale neighbors so small test batches don't crash
        n_neighbors = min(15, n - 1)
        if n_neighbors < 2:
            n_neighbors = 2
            
        coords = umap.UMAP(
            n_components=3,
            n_neighbors=n_neighbors,
            min_dist=0.05,      # Lower = tighter clusters (reduced from 0.1)
            spread=1.2,         # Compact spread for denser clusters
            metric="cosine",    # Cosine is standard for text embeddings
            random_state=42     # Keeps layout stable across API calls
        ).fit_transform(matrix).astype(np.float32)

    # Normalise each axis to [-1, 1] for the frontend UI logic
    # Use a tighter scaling to keep points more concentrated
    for i in range(3):
        lo, hi = coords[:, i].min(), coords[:, i].max()
        span = hi - lo
        if span > 1e-9:
            # Scale to [-0.8, 0.8] instead of [-1, 1] to keep clusters concentrated
            coords[:, i] = (coords[:, i] - lo) / span * 1.6 - 0.8
        else:
            coords[:, i] = 0.0

    return coords


# ---------------------------------------------------------------------------
# Stable colour palette for documents
# ---------------------------------------------------------------------------

# 12 visually distinct colours (hex strings) — cycles if > 12 docs
_DOC_PALETTE = [
    "#d4a843",  # gold
    "#4a9eff",  # blue
    "#52c97a",  # green
    "#e05252",  # red
    "#b96fff",  # purple
    "#ff8c42",  # orange
    "#00d4cc",  # cyan
    "#ff6bbd",  # pink
    "#a8e063",  # lime
    "#ffcc00",  # yellow
    "#7ecfff",  # sky
    "#ff9f7f",  # salmon
]


def _assign_doc_colours(doc_ids: list[str]) -> dict[str, str]:
    """Return a stable doc_id → hex colour mapping."""
    unique = sorted(set(d for d in doc_ids if d))
    return {
        doc_id: _DOC_PALETTE[i % len(_DOC_PALETTE)]
        for i, doc_id in enumerate(unique)
    }


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/viz", tags=["visualization"])


@router.get("/points")
def get_points() -> dict[str, Any]:
    """
    Return chunk embeddings (permanent) + active query embeddings (TTL-gated),
    all reduced to 3D via UMAP.

    Response
    --------
    {
        "count":        int,
        "doc_colours":  { doc_id: hex_colour },
        "centroids":    [ { doc_id, x, y, z, label } ],
        "points": [
            {
                "id", "label", "kind", "doc_id", "page",
                "timestamp", "colour",
                "x", "y", "z",
                "ttl_remaining": float | null   (only for queries)
            }
        ]
    }
    """
    all_records = _load_store()
    if not all_records:
        return {"count": 0, "doc_colours": {}, "centroids": [], "points": []}

    # Separate chunks (permanent) from queries (TTL-gated)
    chunk_records = [r for r in all_records if r.get("kind") != "query"]
    query_records = [r for r in all_records if r.get("kind") == "query" and _is_query_alive(r)]

    # Prune dead queries from store periodically (keep store clean)
    live_records = chunk_records + [r for r in all_records if r.get("kind") == "query"]
    alive_queries_set = {r["id"] for r in query_records}
    pruned = chunk_records + [r for r in all_records if r.get("kind") == "query" and r["id"] in alive_queries_set]
    if len(pruned) < len(all_records):
        _save_store(pruned)

    active_records = chunk_records + query_records

    # Filter to records that have valid vectors
    valid = [
        r for r in active_records
        if isinstance(r.get("vector"), list) and len(r["vector"]) > 2
    ]
    if not valid:
        return {"count": 0, "doc_colours": {}, "centroids": [], "points": []}

    # Build matrix and reduce
    matrix = np.array([r["vector"] for r in valid], dtype=np.float32)
    coords = _reduce_to_3d(matrix)

    # Colour map by doc_id
    doc_ids     = [r.get("doc_id", "") for r in valid]
    doc_colours = _assign_doc_colours(doc_ids)

    now = datetime.now(timezone.utc)
    points = []
    for rec, (x, y, z) in zip(valid, coords):
        is_query = rec.get("kind") == "query"

        # TTL remaining for queries
        ttl_rem = None
        if is_query and rec.get("timestamp"):
            try:
                age     = (now - datetime.fromisoformat(rec["timestamp"])).total_seconds()
                ttl_rem = max(0.0, QUERY_TTL_SECS - age)
            except Exception:
                ttl_rem = None

        colour = "#ffffff" if is_query else doc_colours.get(rec.get("doc_id", ""), _DOC_PALETTE[0])

        points.append({
            "id":            rec.get("id", ""),
            "label":         rec.get("label", ""),
            "kind":          rec.get("kind", "chunk"),
            "doc_id":        rec.get("doc_id", ""),
            "page":          rec.get("page", 1),
            "timestamp":     rec.get("timestamp", ""),
            "colour":        colour,
            "x":             float(x),
            "y":             float(y),
            "z":             float(z),
            "ttl_remaining": ttl_rem,
        })

    # Compute per-document cluster centroids (chunks only)
    centroids = []
    chunk_pts = [p for p in points if p["kind"] == "chunk" and p["doc_id"]]
    by_doc: dict[str, list] = {}
    for p in chunk_pts:
        by_doc.setdefault(p["doc_id"], []).append(p)
    for doc_id, pts in by_doc.items():
        cx = sum(p["x"] for p in pts) / len(pts)
        cy = sum(p["y"] for p in pts) / len(pts)
        cz = sum(p["z"] for p in pts) / len(pts)
        centroids.append({
            "doc_id": doc_id,
            "x": cx, "y": cy, "z": cz,
            "count":  len(pts),
            "colour": doc_colours.get(doc_id, _DOC_PALETTE[0]),
        })

    return {
        "count":       len(points),
        "doc_colours": doc_colours,
        "centroids":   centroids,
        "points":      points,
    }


@router.get("/status")
def get_status() -> dict[str, Any]:
    """Fast count endpoint — no reduction, no GPU."""
    records = _load_store()
    chunks  = [r for r in records if r.get("kind") != "query"]
    queries = [r for r in records if r.get("kind") == "query"]
    alive_q = [r for r in queries if _is_query_alive(r)]
    docs    = list(set(r.get("doc_id", "") for r in chunks if r.get("doc_id")))
    return {
        "chunks":         len(chunks),
        "active_queries": len(alive_q),
        "documents":      len(docs),
        "doc_ids":        docs,
    }


@router.delete("/clear")
def clear_store() -> dict[str, str]:
    _save_store([])
    logger.info("Visualization store cleared")
    return {"status": "cleared"}