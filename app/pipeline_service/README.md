# Pipeline Service

A FastAPI-based orchestration layer that runs OCR, chunking, storage, embedding, and search as a single document processing pipeline.

## Overview

This service coordinates the microservices and exposes HTTP endpoints for:

- document upload and OCR
- human review / confirmation
- chunk generation, storage, embedding, and indexing
- hybrid search and reranking
- chunk metadata retrieval
- original document retrieval

It uses `ocr_service` in a subprocess for Python 3.10 isolation and imports storage, chunk, and embedding modules directly.

## Quick Start

```bash
cd app/pipeline_service
python main.py
```

The service listens on `http://0.0.0.0:8082` by default.

## Startup Behavior

On startup, the pipeline service:

- checks Ceph buckets
- creates `docs` and `chunks` buckets if they do not exist
- prepares temporary folders for OCR and chunk artifacts

## API Endpoints

### `GET /health`

Returns:

- `status`
- current bucket list

### `POST /pipeline/ocr`

Uploads a document, runs OCR, and returns extracted text for review.

Query parameters:

- `document_id` — optional custom document identifier
- `use_orientation` — enable rotation correction (`true`)
- `use_unwarp` — enable unwarping (`true`)
- `use_layout` — enable layout detection (`true`)
- `use_ocr_for_image_block` — OCR image blocks (`false`)
- `use_format` — normalize extracted text (`true`)
- `merge_tables` — merge tables across pages (`false`)

### `POST /pipeline/confirm`

Confirms reviewed text, creates chunks, uploads chunk JSON to Ceph, embeds chunks, and indexes them in OpenSearch.

Query parameters:

- `session_id` — session identifier returned by `/pipeline/ocr`
- `corrected_text` — user-reviewed text
- `max_tokens` — maximum tokens per chunk (default `500`)
- `overlap_ratio` — chunk overlap ratio (default `0.2`)

### `POST /pipeline/query`

Searches indexed documents using hybrid search and reranking.

Query parameters:

- `query_text` — search query text
- `top_k` — number of raw candidates to retrieve (default `50`)
- `rerank_top_n` — number of final reranked results (default `5`)

### `GET /pipeline/chunk/{chunk_id}`

Fetches chunk metadata and content from the stored chunk JSON file in the Ceph `chunks` bucket.

### `GET /pipeline/document/{document_id}`

Returns the original document bytes from the Ceph `docs` bucket.

## Files

- `main.py` — pipeline API and orchestration logic
- `launcher.py` — script to start the pipeline service
- `requirements.txt` — Python dependencies for the service

## Service Flow

1. upload document to Ceph
2. run OCR subprocess
3. review text with Human-in-the-Loop
4. chunk OCR output
5. upload chunks to Ceph
6. embed chunks and index to OpenSearch
7. query with hybrid search + reranking

