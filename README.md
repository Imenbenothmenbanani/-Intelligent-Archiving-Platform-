# Intelligent Document Archiving Platform

## 📌 Purpose

This repository is a complete **Intelligent Document Archiving Platform** designed to extract, index, and search large-scale administrative documents with modern AI techniques.

It is a deployable, multi-service system that combines:

- OCR extraction for scanned images and PDFs
- Layout-aware document reconstruction
- Chunking and token-aware text segmentation
- Vector embeddings for semantic search
- Re-ranking for high-quality retrieval
- Storage, orchestration, frontend, and backend integration

> Use this README as the single source of truth when explaining the project, architecture, and service responsibilities.

---

## 🧠 Project Summary

The platform is built around a **document processing pipeline**. Each stage is implemented as a separate service so components can evolve independently:

1. **Storage Service** — stores original documents, chunk metadata, and archived files in a Ceph/S3-compatible storage layer.
2. **OCR Service** — performs structured OCR using **PaddleOCR-VL** and produces cleaned JSON, Markdown, and visualization outputs.
3. **Chunk Service** — converts OCR JSON into semantic chunks with token counts, overlap handling, and page metadata.
4. **Embedding Service** — embeds chunks and queries using **Qwen3**, and reranks candidate results during search.
5. **Pipeline Service** — orchestrates the full workflow through a FastAPI endpoint layer and manages document ingestion, review, and query handling.
6. **UI / App** — includes an Angular frontend, a Spring Boot backend, and a demo app for visualizing document search results.

---

## 📁 Repository Structure

```
.
├── app/
│   ├── backend-springboot/
│   ├── frontend-angular/
│   └── pipeline_service/
├── chunk_service/
├── demo/
├── embendding_service/
├── ocr_service/
├── storage_service/
└── README.md
```

Each folder represents an independent **service** responsible for a specific pipeline stage.

Every service contains:

- Its own dependencies
- Its own configuration
- A dedicated `README.md` explaining usage and execution

---

## ⚙️ Environment Setup

### 1️⃣ Install pipx (Recommended)

```bash
python -m pip install --user pipx
python -m pipx ensurepath
```

Restart your terminal after installation.

### 2️⃣ Install Poetry using pipx

```bash
pipx install poetry
```

Verify installation:

```bash
poetry --version
```

---

## 🚀 Working with Services

Each service is independent and must be installed separately.

Example:

```bash
cd ocr_service
poetry install
```

Run commands described inside the service README file.

Repeat the same steps for:

- `ocr_service`
- `chunk_service`
- `embedding_service`
- `storage_service`

---

## 🧩 Architecture Pipeline

1. **OCR Service** → Extracts text & layout information from documents
2. **Chunk Service** → Splits structured content into semantic chunks
3. **Embedding Service** → Converts chunks into vector embeddings
4. **Storage Service** → Stores documents, metadata, and vectors
5. **Application Layer** → Provides orchestration and search interface

---

## 📖 Additional Documentation

Detailed instructions, configuration steps, and execution examples are available inside each service directory:

```
<service_name>/README.md
```

---

##
