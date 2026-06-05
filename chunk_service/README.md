# Chunk Service — PaddleOCR JSON to Document Chunks

## Overview

The Chunk Service converts PaddleOCR-VL JSON output into document-level chunks that are ready for embedding and indexing.

It is implemented in `main.py`, which calls `build_chunks(...)` from `chunk_builder.py`.

## Installation

```bash
cd chunk_service
poetry install
```

## CLI Usage

```bash
poetry run python main.py --input path/to/document.json
```

### Options

- `--input` — path to a PaddleOCR JSON file
- `--output` — directory to save chunk JSON files (default: `./chunks`)
- `--max-tokens` — maximum tokens per chunk (default: `500`)
- `--min-tokens` — minimum tokens per chunk (default: `150`)
- `--overlap` — chunk overlap ratio between 0 and 1 (default: `0.2`)
- `--dry-run` — print chunk statistics without writing output

### Example

```bash
poetry run python main.py \
  --input ./ocr_output/document.json \
  --output ./chunks \
  --max-tokens 500 \
  --overlap 0.2
```

## Output Format

The service writes a JSON file for the document, typically named:

```
<document_id>_chunks.json
```

Each chunk contains metadata such as:

- `chunk_id` — unique chunk identifier
- `document_id` — original document base name
- `page` — source page number
- `chunk_index` — chunk position index
- `text` — chunk text content
- `token_count` — token count for the chunk
- `bbox` — bounding box covering merged OCR blocks
- `block_ids` — original OCR block IDs included in the chunk
- `contains_image_ocr` — whether the chunk contains OCR from image blocks

## How It Works

`build_chunks(...)` reads OCR JSON, tokenizes text, and creates overlapping chunks using the specified `max_tokens`, `min_tokens`, and `overlap_ratio`.

## Role in the Pipeline

```
Document → OCR Service → Chunk Service → Embedding Service
```

The chunk output is consumed by the embedding service for vector indexing.

