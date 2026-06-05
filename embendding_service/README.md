# Embedding & Reranking Service — Qwen3 Pipeline

## Overview

This service converts document chunks into vector embeddings, indexes them into OpenSearch, and reranks retrieved candidates during query time.

It includes:

- `embedder.py` — chunk embedding, query embedding, and search orchestration
- `opensearch_client.py` — OpenSearch index creation, document indexing, and hybrid search
- `reranker.py` — candidate reranking using Qwen3 scoring
- `main.py` — CLI for indexing, query embedding, and reranking

## Installation

```bash
cd embendding_service
poetry install
```

## How It Works

### Indexing

1. `index_chunks(...)` reads chunk JSON
2. Generates Qwen3 embeddings for each chunk
3. Calls `index_doc(...)` to store each chunk in OpenSearch

### Retrieval

1. `search(...)` embeds the query
2. Executes a hybrid OpenSearch search combining BM25 and kNN
3. Returns top-K hits for reranking

### Reranking

`rerank(...)` scores candidates with a Qwen3 reranker prompt and returns a ranked result list.

## Core Retrieval Method

This project uses a hybrid retrieval method:

- BM25 full-text search on the `text` field
- kNN vector search on the `embedding` field
- OpenSearch hybrid pipeline combines the scores

The OpenSearch index is configured with:

- `embedding` as `knn_vector`
- `space_type: cosinesimil`
- HNSW index parameters
- a search pipeline that normalizes scores and computes an arithmetic mean

## CLI Usage

```bash
poetry run python main.py index --file <chunks.json>
poetry run python main.py query --text "Search query"
poetry run python main.py rerank --query "Search query" --candidates candidates.json --top-n 10
```

### Commands

- `index` — embed chunks and optionally upload them to OpenSearch
- `query` — embed a query and save the vector
- `rerank` — rerank candidate hits with the reranker model

## Outputs

- `chunks_embedded.json` — embedded chunk documents
- `query_embedding.json` — query embedding vector
- `rerank_results.json` — reranked candidates output

## Files

- `embedder.py` — embedding and search logic
- `opensearch_client.py` — OpenSearch index and hybrid retrieval
- `reranker.py` — candidate reranker logic
- `main.py` — CLI interface

## Role in the Pipeline

```
Document → OCR Service → Chunk Service → Embedding Service → OpenSearch → Query + Rerank
```

The embedding service is responsible for producing indexed document vectors and serving search candidates to the reranker.

Structure:

```json
{
  "query": "example query",
  "embedding": [0.11, -0.22, ...]
}
```

---

### 🔹 3. Reranker Output

File:

```
rerank_results.json
```

Structure:

```json
[
  {
    "rank": 1,
    "chunk_id": "chunk_5",
    "rerank_score": 0.92,
    "first_stage_score": 0.81,
    "text": "Relevant chunk text..."
  }
]
```

---

## 🧠 Important Design Notes

### ✔️ Asymmetric Embedding

* Documents → neutral embeddings
* Queries → guided by instruct

---

### ✔️ Reranker Behavior

* Completely **reorders results**
* Scores are **NOT comparable** to embedding similarity
* Focuses on **semantic relevance**

---

### ✔️ Chunk Pointer Design

Only `chunk_id` is stored in results.

➡️ All metadata is retrieved later from original chunk files.

---

## 🔎 OpenSearch Integration

### Setup: Initialize Hybrid Pipeline

Before running queries through the system, you must **create the `hybrid-pipeline` in OpenSearch**.

This pipeline combines BM25 (full-text search) and kNN (vector search) results using arithmetic mean scoring.

#### 1️⃣ Run Setup Script (First Time Only)

```bash
poetry run python setup_pipeline.py
```

This script will:
- Check if OpenSearch is running at the URL in `config/.env`
- Create the `hybrid-pipeline` with arithmetic mean combination
- Report success or any errors

**Output:**
```
OpenSearch Hybrid Pipeline Setup
==============================================================================
OpenSearch URL: http://localhost:9200

✓ OpenSearch is reachable
Pipeline 'hybrid-pipeline' not found

Creating pipeline at: http://localhost:9200/_search/pipeline/hybrid-pipeline
Pipeline body: {...}
Status: 201
✓ Pipeline created successfully!

Setup complete!
```

#### 2️⃣ Configuration

The pipeline name is defined in `config/config.py`:

```python
PIPELINE_NAME = "hybrid-pipeline"
```

If you change the pipeline name, update both:
1. `config/config.py`
2. Rerun `setup_pipeline.py`

#### 3️⃣ Troubleshooting

**Error: "Cannot reach OpenSearch"**
- Ensure OpenSearch is running: `docker-compose up` (or your startup method)
- Check `config/.env` has correct `OPENSEARCH_HOST` and `OPENSEARCH_PORT`

**Error: "Pipeline hybrid-pipeline is not defined" (HTTP 400)**
- Run `poetry run python setup_pipeline.py` again
- Check OpenSearch Dashboard → Search Pipeline Management

**Pipeline already exists (HTTP 409)**
- This is OK — the pipeline is already configured
- You can change OpenSearch configuration in OpenSearch Dashboard if needed

---

## 📖 Related Documentation

Refer to the main repository README for overall architecture and environment setup.
