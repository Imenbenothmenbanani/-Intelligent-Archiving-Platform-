"""
reranker.py — Qwen3-Reranker-0.6B reranking utilities

Model loading strategy
-----------------------
Both the tokenizer and the model are loaded exactly ONCE per process via
module-level singletons (_reranker_tokenizer, _reranker_model).  Every
subsequent call to _load_reranker() returns the cached objects immediately.

Only chunk_id is carried through the pipeline as a pointer to the original
chunk JSON for page, bbox, block_ids, document_id, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

RERANKER_MODEL = "Qwen/Qwen3-Reranker-0.6B"

DEFAULT_RERANKER_INSTRUCT = (
    "Given a user question, judge whether the following document passage directly answers or addresses it. "
    "The document may be in French, Arabic, or English."
)

MAX_LENGTH = 8192
BATCH_SIZE = 8

# ── Process-level singleton — loaded ONCE, reused forever ─────────────────────
_reranker_model:     AutoModelForCausalLM | None = None
_reranker_tokenizer: AutoTokenizer        | None = None


@dataclass
class Candidate:
    chunk_id: str
    text:     str
    score:    float = 0.0


@dataclass
class RankedResult:
    rank:              int
    chunk_id:          str
    text:              str
    rerank_score:      float
    first_stage_score: float


def _load_reranker() -> tuple[AutoTokenizer, AutoModelForCausalLM]:
    """
    Return (tokenizer, model).  The model is loaded from disk on the very
    first call; every subsequent call returns the cached objects immediately.
    """
    global _reranker_model, _reranker_tokenizer

    if _reranker_model is not None:
        # Fast path — already loaded
        return _reranker_tokenizer, _reranker_model

    import logging
    logging.getLogger(__name__).info("Loading Qwen3-Reranker-0.6B … (first call only)")

    _reranker_tokenizer = AutoTokenizer.from_pretrained(RERANKER_MODEL, padding_side="left")

    try:
        _reranker_model = AutoModelForCausalLM.from_pretrained(
            RERANKER_MODEL,
            torch_dtype=torch.float16,
            attn_implementation="sdpa",
        )
    except (ValueError, ImportError):
        _reranker_model = AutoModelForCausalLM.from_pretrained(
            RERANKER_MODEL, torch_dtype=torch.float16
        )

    _reranker_model.eval()
    _reranker_model.to("cuda" if torch.cuda.is_available() else "cpu")

    import logging
    logging.getLogger(__name__).info(
        "Qwen3-Reranker-0.6B loaded on %s",
        "cuda" if torch.cuda.is_available() else "cpu",
    )
    return _reranker_tokenizer, _reranker_model


# ── Internals ─────────────────────────────────────────────────────────────────

def _build_prompt(query: str, document: str, instruct: str) -> str:
    return f"{instruct}\nQuery: {query}\nDocument: {document}\nRelevant: "


def _get_yes_no_token_ids(tokenizer: AutoTokenizer) -> tuple[int, int]:
    yes_ids = tokenizer.encode("yes", add_special_tokens=False)
    no_ids  = tokenizer.encode("no",  add_special_tokens=False)
    if len(yes_ids) != 1 or len(no_ids) != 1:
        raise ValueError(
            f"'yes'/'no' must each map to a single token. Got yes={yes_ids}, no={no_ids}"
        )
    return yes_ids[0], no_ids[0]


def _score_batch(
    prompts:   list[str],
    tokenizer: AutoTokenizer,
    model:     AutoModelForCausalLM,
    yes_id:    int,
    no_id:     int,
) -> list[float]:
    device = next(model.parameters()).device
    encoded = tokenizer(
        prompts,
        padding=True,
        truncation=True,
        max_length=MAX_LENGTH,
        return_tensors="pt",
    ).to(device)

    with torch.no_grad():
        logits = model(**encoded).logits[:, -1, :]

    scores = (
        torch.stack([logits[:, yes_id], logits[:, no_id]], dim=-1)
        .softmax(dim=-1)[:, 0]
    )

    del encoded, logits
    if device.type == "cuda":
        torch.cuda.empty_cache()

    return scores.cpu().float().tolist()


# ── Public API ────────────────────────────────────────────────────────────────

def rerank(
    query:      str,
    candidates: list[Candidate],
    top_n:      int | None = None,
    instruct:   str = DEFAULT_RERANKER_INSTRUCT,
    batch_size: int = BATCH_SIZE,
) -> list[RankedResult]:
    """
    Rerank *candidates* against *query*.
    Uses the cached singleton model — no reloading between calls.
    """
    if not candidates:
        return []

    tokenizer, model = _load_reranker()
    yes_id, no_id    = _get_yes_no_token_ids(tokenizer)
    prompts          = [_build_prompt(query, c.text, instruct) for c in candidates]

    all_scores: list[float] = []
    for i in range(0, len(prompts), batch_size):
        all_scores.extend(
            _score_batch(prompts[i : i + batch_size], tokenizer, model, yes_id, no_id)
        )

    paired  = sorted(zip(candidates, all_scores), key=lambda x: x[1], reverse=True)
    results = [
        RankedResult(
            rank=rank,
            chunk_id=c.chunk_id,
            text=c.text,
            rerank_score=score,
            first_stage_score=c.score,
        )
        for rank, (c, score) in enumerate(paired, start=1)
    ]

    return results[:top_n] if top_n is not None else results


def candidates_from_hits(hits: list[dict[str, Any]]) -> list[Candidate]:
    """Convert raw OpenSearch hits into Candidate objects."""
    candidates = []
    for i, h in enumerate(hits):
        if "_source" in h:
            chunk_id = h.get("_id", str(i))
            text     = h["_source"].get("text", "")
            score    = h.get("_score", 0.0)
        elif "_id" in h:
            chunk_id = h["_id"]
            text     = h.get("text", "")
            score    = h.get("score", 0.0)
        else:
            chunk_id = h.get("chunk_id", str(i))
            text     = h.get("text", "")
            score    = h.get("score", 0.0)
        candidates.append(Candidate(chunk_id=chunk_id, text=text, score=score))
    return candidates