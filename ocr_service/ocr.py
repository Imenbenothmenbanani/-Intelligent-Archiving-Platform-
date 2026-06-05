"""
ocr.py — PaddleOCR-VL Engine
------------------------------
Reusable OCR pipeline wrapper. Load once, call many times.
Import and use OCRPipeline directly, or call run_ocr() for single-file processing.
"""

import gc
import os
import time
import logging
from pathlib import Path
from typing import Optional

import torch

# ── Bypass PaddlePaddle connectivity check before any paddle import ────────────
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from paddleocr import PaddleOCRVL

# ── Logging ────────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff"}
)


# ==============================================================================
# Memory Utilities
# ==============================================================================

def _release_memory() -> None:
    """Force GPU + CPU memory release to prevent fragmentation / OOM."""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


# ==============================================================================
# Pipeline Wrapper — load ONCE, reuse everywhere
# ==============================================================================

class OCRPipeline:
    """
    Wraps PaddleOCRVL so the model is loaded exactly once.

    Usage
    -----
    pipeline = OCRPipeline()                  # load once
    result   = pipeline.process("doc.pdf")    # call N times
    """

    def __init__(
        self,
        *,
        use_doc_orientation_classify: bool = True,
        use_doc_unwarping: bool = True,
        use_layout_detection: bool = True,
        use_ocr_for_image_block: bool = True,
        format_block_content: bool = True,
        merge_layout_blocks: bool = False,
    ) -> None:
        logger.info("Initializing PaddleOCR-VL pipeline …")
        self._pipeline = PaddleOCRVL(
            use_doc_orientation_classify=use_doc_orientation_classify,
            use_doc_unwarping=use_doc_unwarping,
            use_layout_detection=use_layout_detection,
            use_ocr_for_image_block=use_ocr_for_image_block,
            format_block_content=format_block_content,
            merge_layout_blocks=merge_layout_blocks,
        )
        logger.info("Pipeline ready.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        input_path: str | Path,
        *,
        output_root: str | Path = "ocr_output",
        draw_layout: bool = False,
        merge_tables: bool = False,
    ) -> dict:
        """
        Run OCR on a single file.

        Parameters
        ----------
        input_path   : Path to the input image or PDF.
        output_root  : Root directory for all outputs.
        draw_layout  : Whether to save layout visualisation images.
        merge_tables : Whether to merge tables that span multiple pages.

        Returns
        -------
        dict with keys:
            output_dir       – absolute path of the results folder
            processing_time  – wall-clock seconds for inference + save
        """
        input_path = Path(input_path)
        self._validate(input_path)

        output_dir = Path(output_root) / input_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Processing: %s", input_path.name)
        t0 = time.perf_counter()

        # 1. Predict
        raw_results = self._pipeline.predict(str(input_path), return_cls=True)

        # 2. Restructure pages
        structured = self._pipeline.restructure_pages(
            raw_results,
            merge_tables=merge_tables,
            relevel_titles=True,
            concatenate_pages=True,
        )

        elapsed = time.perf_counter() - t0
        logger.info("Inference done in %.2fs", elapsed)

        # 3. Save results, release each page immediately
        self._save_results(structured, output_dir, draw_layout)

        # 4. Post-document memory cleanup
        _release_memory()

        logger.info("Results saved → %s", output_dir)
        return {
            "output_dir": str(output_dir.resolve()),
            "processing_time": round(elapsed, 3),
        }

    def process_batch(
        self,
        input_paths: list[str | Path],
        *,
        output_root: str | Path = "ocr_output",
        draw_layout: bool = False,
        merge_tables: bool = False,
    ) -> list[dict]:
        """
        Run OCR on multiple files using the same loaded pipeline.

        Returns a list of result dicts (one per input file).
        Failed files are included with an 'error' key instead of 'output_dir'.
        """
        results = []
        for path in input_paths:
            try:
                result = self.process(
                    path,
                    output_root=output_root,
                    draw_layout=draw_layout,
                    merge_tables=merge_tables,
                )
                results.append({"input": str(path), **result})
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to process %s: %s", path, exc)
                results.append({"input": str(path), "error": str(exc)})
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{path.suffix}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

    @staticmethod
    def _save_results(structured, output_dir: Path, draw_layout: bool) -> None:
        for res in structured:
            res.save_to_json(save_path=str(output_dir))
            res.save_to_markdown(save_path=str(output_dir))
            if draw_layout:
                res.save_to_img(save_path=str(output_dir))
            del res


# ==============================================================================
# Convenience function (single-file, no class needed)
# ==============================================================================

def run_ocr(
    input_path: str | Path,
    *,
    output_root: str | Path = "ocr_output",
    draw_layout: bool = False,
    merge_tables: bool = False,
    merge_layout_blocks: bool = False,
    pipeline: Optional["OCRPipeline"] = None,
) -> dict:
    """
    One-shot helper: create a pipeline (or reuse a provided one) and process
    a single file. Convenient for scripted / library usage.

    If you process multiple files, pass your own OCRPipeline instance so the
    model is not reloaded on every call.
    """
    _pipeline = pipeline or OCRPipeline(merge_layout_blocks=merge_layout_blocks)
    return _pipeline.process(
        input_path,
        output_root=output_root,
        draw_layout=draw_layout,
        merge_tables=merge_tables,
    )