# OCR Service — PaddleOCR-VL

## Overview

The OCR Service extracts structured text, layout, and document information from scanned images and PDF files using **PaddleOCR-VL**.

The service is implemented in `main.py`, which builds the OCR pipeline and processes one or more input files.

## Supported Inputs

- Image files: `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`
- Documents: `.pdf`

## Installation

```bash
cd ocr_service
poetry install
```

## CLI Usage

```bash
poetry run python main.py --input path/to/file.pdf
```

### Available options

- `--input` — one or more input files
- `--output` — output directory (default: `ocr_output`)
- `--orientation` — enable document orientation correction
- `--unwarp` — enable perspective unwarping
- `--layout` — enable layout detection
- `--ocr-images` — run OCR inside detected image blocks
- `--format` — normalize and clean extracted text blocks
- `--merge-layout` — merge adjacent layout blocks
- `--layout-imgs` — save layout visualization images
- `--merge-tables` — merge tables spanning multiple pages

### Example

```bash
poetry run python main.py \
  --input scan.pdf \
  --output ./ocr_output \
  --orientation \
  --unwarp \
  --layout \
  --format \
  --merge-layout
```

## Output

For each processed document, the service writes:

- `result.json` — structured OCR output
- `result.md` — markdown-formatted text
- visualizations when `--layout-imgs` is enabled

Output appears under `ocr_output/<document_name>/` by default.

## What the Pipeline Does

`main.py` initializes the `OCRPipeline` with the chosen options and processes files in batch.

It supports:

- orientation correction
- unwarping / perspective correction
- layout detection
- OCR inside image blocks
- normalized text output
- merged tables across pages

## Role in the System

```
Document → Storage Service → OCR Service → Chunk Service → Embedding Service
```

The OCR Service produces the structured JSON input consumed by the Chunk Service.

## Related Files

- `main.py` — CLI entry point and argument parsing
- `ocr.py` — OCR pipeline implementation
- `ocr_output/` — default output directory

