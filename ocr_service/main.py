"""
main.py — CLI entry point for the OCR Service
----------------------------------------------
Loads the PaddleOCR-VL pipeline ONCE, then processes one or more files.
All OCR logic lives in ocr.py — this file handles argument parsing only.

Pipeline option flags
---------------------
Every PaddleOCR-VL boolean switch is now a CLI flag so the parent process
(pipeline_index._run_ocr_subprocess) can forward the user's choices from
the UI without touching this file:

  --orientation   use_doc_orientation_classify   (default OFF → pass flag to ON)
  --unwarp        use_doc_unwarping
  --layout        use_layout_detection
  --ocr-images    use_ocr_for_image_block
  --format        format_block_content
  --merge-layout  merge_layout_blocks

Usage examples
--------------
# All options off (minimal)
poetry run python main.py --input document.pdf

# All options on (richest output)
poetry run python main.py --input scan.jpg \\
    --orientation --unwarp --layout --ocr-images --format

# Save visualisation images + merge layout
poetry run python main.py --input a.pdf --layout --merge-layout --layout-imgs

# Multiple files, options shared
poetry run python main.py --input a.pdf b.png --orientation --layout --output ./out
"""

import sys
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from ocr import OCRPipeline  # noqa: E402

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ==============================================================================
# Argument Parser
# ==============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocr-service",
        description=(
            "PaddleOCR-VL Document Processor — extracts structured text "
            "from images and PDFs with configurable pipeline options."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
pipeline options (each is OFF by default; pass the flag to enable):
  --orientation   Correct document rotation / orientation
  --unwarp        Correct perspective distortion
  --layout        Detect document layout (titles, tables, …)
  --ocr-images    Run OCR inside detected image blocks
  --format        Normalise / clean extracted text blocks
  --merge-layout  Merge adjacent layout blocks

other options:
  --layout-imgs   Save layout visualisation images  (was --layout in old CLI)
  --merge-tables  Merge tables that span multiple pages

examples:
  poetry run python main.py --input scan.pdf --orientation --unwarp --layout
  poetry run python main.py --input a.pdf b.png --layout --format --output ./out
""",
    )

    parser.add_argument(
        "--input", required=True, nargs="+", metavar="FILE",
        help="One or more input files (images or PDFs).",
    )
    parser.add_argument(
        "--output", default="ocr_output", metavar="DIR",
        help="Root output directory (default: ocr_output).",
    )

    # ── PaddleOCR-VL pipeline option flags ────────────────────────────────────
    parser.add_argument(
        "--orientation", action="store_true",
        help="Enable use_doc_orientation_classify.",
    )
    parser.add_argument(
        "--unwarp", action="store_true",
        help="Enable use_doc_unwarping.",
    )
    parser.add_argument(
        "--layout", action="store_true",
        help="Enable use_layout_detection.",
    )
    parser.add_argument(
        "--ocr-images", dest="ocr_images", action="store_true",
        help="Enable use_ocr_for_image_block.",
    )
    parser.add_argument(
        "--format", action="store_true",
        help="Enable format_block_content.",
    )
    parser.add_argument(
        "--merge-layout", dest="merge_layout", action="store_true",
        help="Enable merge_layout_blocks.",
    )

    # ── Output/post-processing flags ──────────────────────────────────────────
    parser.add_argument(
        "--layout-imgs", dest="layout_imgs", action="store_true",
        help="Save layout visualisation images alongside JSON/Markdown.",
    )
    parser.add_argument(
        "--merge-tables", dest="merge_tables", action="store_true",
        help="Merge tables that span multiple pages.",
    )

    return parser


# ==============================================================================
# Main
# ==============================================================================

def main() -> int:
    parser = build_parser()
    args   = parser.parse_args()

    input_files = [Path(p) for p in args.input]

    # Pre-flight: validate all paths before loading the (heavy) model
    missing = [p for p in input_files if not p.exists()]
    if missing:
        for p in missing:
            logger.error("File not found: %s", p)
        return 2

    # Build pipeline kwargs from flags
    pipeline_kwargs = dict(
        use_doc_orientation_classify = args.orientation,
        use_doc_unwarping            = args.unwarp,
        use_layout_detection         = args.layout,
        use_ocr_for_image_block      = args.ocr_images,
        format_block_content         = args.format,
        merge_layout_blocks          = args.merge_layout,
    )

    logger.info("Pipeline options: %s", pipeline_kwargs)

    # Load pipeline ONCE
    logger.info("Initializing pipeline …")
    try:
        pipeline = OCRPipeline(**pipeline_kwargs)
    except Exception as exc:
        logger.error("Failed to initialize pipeline: %s", exc)
        return 2

    # Process all files
    process_kwargs = dict(
        output_root  = args.output,
        draw_layout  = args.layout_imgs,
        merge_tables = args.merge_tables,
    )

    if len(input_files) == 1:
        result = pipeline.process(input_files[0], **process_kwargs)
        result["input"] = str(input_files[0])
        results = [result]
    else:
        results = pipeline.process_batch(input_files, **process_kwargs)

    # Report
    print("\n" + "=" * 60)
    print(f"  Processed {len(results)} file(s)")
    print("=" * 60)

    errors = 0
    total_time = 0.0
    for r in results:
        if "error" in r:
            errors += 1
            print(f"  [ERROR] {r['input']}")
            print(f"          {r['error']}")
        else:
            total_time += r.get("processing_time", 0)
            print(f"  [OK]    {r['input']}")
            print(f"          Output : {r['output_dir']}")
            print(f"          Time   : {r['processing_time']:.2f}s")

    print("-" * 60)
    print(f"  Total: {total_time:.2f}s   Errors: {errors}/{len(results)}")
    print("=" * 60 + "\n")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())