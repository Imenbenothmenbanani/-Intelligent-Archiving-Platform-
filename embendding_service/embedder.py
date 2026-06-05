"""
embedder.py — Qwen3-Embedding-0.6B embedding utilities

Model loading strategy
-----------------------
Both the tokenizer and the model are loaded exactly ONCE per process via a
module-level singleton (_tokenizer, _model).  Any subsequent call to
_load_model() returns the cached objects immediately — no GPU re-allocation,
no disk re-read, no extra latency.

OpenSearch document shape:
    { "_id": "chunk_id", "chunk_id": "chunk_id", "text": "...", "embedding": [...] }
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

# ── Config resolution (unchanged from original) ───────────────────────────────
_SERVICE_DIR = Path(__file__).parent
_CONFIG_DIR  = _SERVICE_DIR / "config"
if str(_CONFIG_DIR) not in sys.path:
    sys.path.insert(0, str(_CONFIG_DIR))
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

_config_module_name = "__embedding_config__"
if _config_module_name not in sys.modules:
    _config_py_path = _CONFIG_DIR / "config.py"
    _config_spec    = importlib.util.spec_from_file_location(_config_module_name, _config_py_path)
    _config_mod     = importlib.util.module_from_spec(_config_spec)
    _config_mod.__file__ = str(_config_py_path)
    sys.modules[_config_module_name] = _config_mod
    _config_spec.loader.exec_module(_config_mod)

KNN_TOP_K = sys.modules[_config_module_name].KNN_TOP_K

import numpy as np
import torch
from torch import Tensor
from transformers import AutoModel, AutoTokenizer

from opensearch_client import hybrid_search, index_doc

# ── Model constants ───────────────────────────────────────────────────────────
MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"

DEFAULT_INDEX_INSTRUCT = None
DEFAULT_QUERY_INSTRUCT = (
    "Instruct: Retrieve semantically relevant passages that address the meaning and intent of the question, "
    "focusing on conceptual similarity rather than keyword overlap, regardless of the document language.\nQuery: "
)

MAX_LENGTH = 8192
BATCH_SIZE = 16

# ── Process-level singleton — loaded ONCE, reused forever ─────────────────────
_model:     AutoModel     | None = None
_tokenizer: AutoTokenizer | None = None


def _load_model() -> tuple[AutoTokenizer, AutoModel]:
    """
    Return (tokenizer, model).  The model is loaded from disk on the very
    first call; every subsequent call returns the cached objects immediately.

    Thread safety: CPython's GIL makes the check-and-load pattern safe for
    typical single-threaded FastAPI (uvicorn) workers.  For multi-threaded
    scenarios a threading.Lock() can be added around the load block.
    """
    global _model, _tokenizer

    if _model is not None:
        # Fast path — already loaded
        return _tokenizer, _model

    import logging
    logging.getLogger(__name__).info("Loading Qwen3-Embedding-0.6B … (first call only)")

    _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, padding_side="left")

    try:
        _model = AutoModel.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.float16,
            attn_implementation="sdpa",
        )
    except (ValueError, ImportError):
        _model = AutoModel.from_pretrained(MODEL_NAME, torch_dtype=torch.float16)

    _model.eval()
    _model.to("cuda" if torch.cuda.is_available() else "cpu")

    import logging
    logging.getLogger(__name__).info(
        "Qwen3-Embedding-0.6B loaded on %s",
        "cuda" if torch.cuda.is_available() else "cpu",
    )
    return _tokenizer, _model


# ── Internal encoding ─────────────────────────────────────────────────────────

def _last_token_pool(hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
    seq_lens = attention_mask.sum(dim=1) - 1
    return hidden_states[
        torch.arange(hidden_states.size(0), device=hidden_states.device), seq_lens
    ]


def _encode(
    texts:      list[str],
    instruct:   str | None = None,
    batch_size: int = BATCH_SIZE,
) -> np.ndarray:
    """
    Encode a list of texts into normalised float32 vectors.
    Uses the cached singleton model — no reloading between calls.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Validate input
    if not texts:
        logger.error("_encode() received empty texts list")
        raise ValueError("Cannot encode empty list of texts — check if chunks have valid 'text' field")
    
    tokenizer, model = _load_model()
    device  = next(model.parameters()).device
    inputs  = texts if instruct is None else [f"{instruct}{t}" for t in texts]

    all_vecs: list[Tensor] = []
    for i in range(0, len(inputs), batch_size):
        encoded = tokenizer(
            inputs[i : i + batch_size],
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors="pt",
        ).to(device)

        with torch.no_grad():
            out = model(**encoded)

        vecs = _last_token_pool(out.last_hidden_state, encoded["attention_mask"])
        vecs = torch.nn.functional.normalize(vecs, p=2, dim=-1)
        all_vecs.append(vecs.cpu().float())

        del encoded, out, vecs
        if device.type == "cuda":
            torch.cuda.empty_cache()

    if not all_vecs:
        logger.error("No vectors were created during encoding — this should not happen")
        raise RuntimeError("Encoding failed: no vectors produced")
    
    return torch.cat(all_vecs, dim=0).numpy()


# ── Public API ────────────────────────────────────────────────────────────────

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def top_k_indices(query_vec: np.ndarray, corpus_vecs: np.ndarray, k: int = 10) -> list[int]:
    scores = corpus_vecs @ query_vec
    return np.argsort(scores)[::-1][:k].tolist()


def load_chunks(json_file: str | Path) -> list[dict[str, Any]]:
    path = Path(json_file)
    if not path.exists():
        raise FileNotFoundError(f"Chunk file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        return raw.get("chunks", [])
    if isinstance(raw, list):
        return raw
    raise ValueError(f"Unsupported JSON structure in {path}")


def index_chunks(
    json_file: str | Path,
    instruct:  str | None = DEFAULT_INDEX_INSTRUCT,
    upload:    bool = True,
) -> list[dict[str, Any]]:
    """
    Load chunks, embed them with the singleton model, and optionally index
    them into OpenSearch.

    The model is loaded on the first call and reused on all subsequent calls.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    chunks  = load_chunks(json_file)
    logger.info(f"Loaded {len(chunks)} chunks from {json_file}")
    
    if not chunks:
        raise ValueError(f"No chunks loaded from {json_file} — check if file is empty or malformed")
    
    # Check for empty texts
    chunks_with_text = [c for c in chunks if c.get("text", "").strip()]
    empty_text_count = len(chunks) - len(chunks_with_text)
    
    if empty_text_count > 0:
        logger.warning(f"{empty_text_count} out of {len(chunks)} chunks have empty text field")
    
    if not chunks_with_text:
        raise ValueError(f"All {len(chunks)} chunks have empty text fields — check chunk generation")
    
    texts = [c["text"] for c in chunks_with_text]
    logger.info(f"Encoding {len(texts)} non-empty chunks")
    vectors = _encode(texts, instruct=instruct)

    docs = [
        {
            "_id":       chunk["chunk_id"],
            "text":      chunk["text"],
            "embedding": vec.tolist(),
        }
        for chunk, vec in zip(chunks_with_text, vectors)
    ]

    if upload:
        index_doc(docs)

    return docs


def embed_query(query: str, instruct: str | None = DEFAULT_QUERY_INSTRUCT) -> np.ndarray:
    """
    Encode a single query string into a normalised embedding vector.
    Uses the cached singleton model — zero overhead after the first call.
    """
    return _encode([query], instruct=instruct)[0]


def search(
    query:    str,
    top_k:    int = KNN_TOP_K,
    instruct: str | None = DEFAULT_QUERY_INSTRUCT,
) -> list[dict]:
    """
    Embed query → hybrid BM25 + kNN search in OpenSearch → return hits.
    """
    query_vector = embed_query(query, instruct=instruct)
    return hybrid_search(
        query_vector=query_vector.tolist(),
        query_text=query,
        top_k=top_k,
    )