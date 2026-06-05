import argparse
import json
from pathlib import Path
from chunk_builder import build_chunks

def main():
    parser = argparse.ArgumentParser(description="PaddleOCR JSON → Document-level Chunks")
    parser.add_argument("--input", required=True, help="Path to PaddleOCR-VL JSON file")
    parser.add_argument("--output", default="./chunks", help="Directory to store chunked JSON")
    parser.add_argument("--max-tokens", type=int, default=500, help="Max tokens per chunk")
    parser.add_argument("--min-tokens", type=int, default=150, help="Min tokens per chunk")
    parser.add_argument("--overlap", type=float, default=0.2, help="Overlap ratio (0-1)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write output, only print stats")

    args = parser.parse_args()

    input_path = Path(args.input)
    document_id = input_path.stem  # auto from filename

    with open(input_path, "r", encoding="utf-8") as f:
        ocr_json = json.load(f)

    build_chunks(
        ocr_json=ocr_json,
        document_id=document_id,
        max_tokens=args.max_tokens,
        min_tokens=args.min_tokens,
        overlap_ratio=args.overlap,
        dry_run=args.dry_run,
        output_dir=args.output
    )

if __name__ == "__main__":
    main()