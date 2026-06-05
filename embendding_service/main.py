from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from embedder import DEFAULT_INDEX_INSTRUCT, DEFAULT_QUERY_INSTRUCT, embed_query, index_chunks
from reranker import DEFAULT_RERANKER_INSTRUCT, candidates_from_hits, rerank

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def cmd_index(args: argparse.Namespace) -> None:
    print(f"[*] Embedding chunks from: {args.file}")
    t0 = time.perf_counter()
    try:
        docs = index_chunks(args.file, instruct=DEFAULT_INDEX_INSTRUCT)
    except FileNotFoundError as e:
        print(f"[!] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[+] Embedded {len(docs)} chunks in {time.perf_counter() - t0:.2f}s")

    if args.preview and docs:
        d = docs[0]
        print(f"\n[Preview - First Document]")
        print(f"  _id: {d['_id']}")
        print(f"  text: {d['text'][:100]}...")
        print(f"  embedding dim: {len(d['embedding'])}")

    out_path = OUTPUT_DIR / (Path(args.file).stem + "_embedded.json")
    out_path.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] Saved to: {out_path}")


def cmd_query(args: argparse.Namespace) -> None:
    print(f"[*] Embedding query: {args.text!r}")
    vec = embed_query(args.text, instruct=DEFAULT_QUERY_INSTRUCT)
    print(f"[+] Embedding dimension: {vec.shape[0]}")
    print(f"[+] Norm: {float((vec**2).sum()**0.5):.6f}")

    out_path = OUTPUT_DIR / "query_embedding.json"
    out_path.write_text(
        json.dumps({"query": args.text, "embedding": vec.tolist()}, indent=2),
        encoding="utf-8",
    )
    print(f"[+] Saved to: {out_path}")


def cmd_rerank(args: argparse.Namespace) -> None:
    cand_path = Path(args.candidates)
    if not cand_path.exists():
        print(f"[!] File not found: {cand_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Reranking: {args.query!r}")
    candidates = candidates_from_hits(json.loads(cand_path.read_text(encoding="utf-8")))
    print(f"[*] Loaded {len(candidates)} candidates")

    t0 = time.perf_counter()
    results = rerank(args.query, candidates, top_n=args.top_n, instruct=DEFAULT_RERANKER_INSTRUCT)
    print(f"[+] Reranked in {time.perf_counter() - t0:.2f}s")

    print(f"\n[Top {len(results)} Results]")
    for r in results:
        print(f"  #{r.rank:2d} | {r.chunk_id:20s} | score={r.rerank_score:.4f} | {r.text[:60]}...")

    out_path = OUTPUT_DIR / "rerank_results.json"
    out_path.write_text(
        json.dumps(
            [{"rank": r.rank, "chunk_id": r.chunk_id, "rerank_score": r.rerank_score,
              "first_stage_score": r.first_stage_score, "text": r.text} for r in results],
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[+] Saved to: {out_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description="Qwen3 Embedding & Reranker CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Embed chunks from JSON")
    p_index.add_argument("--file", required=True)
    p_index.add_argument("--preview", action="store_true")
    p_index.set_defaults(func=cmd_index)

    p_query = sub.add_parser("query", help="Embed a query")
    p_query.add_argument("--text", required=True)
    p_query.set_defaults(func=cmd_query)

    p_rerank = sub.add_parser("rerank", help="Rerank candidates")
    p_rerank.add_argument("--query", required=True)
    p_rerank.add_argument("--candidates", required=True)
    p_rerank.add_argument("--top-n", type=int, default=10, dest="top_n")
    p_rerank.set_defaults(func=cmd_rerank)

    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)