# App Layer

This folder contains the application layer for the Intelligent Archiving Platform.

## Contents

- `pipeline_service/` — FastAPI orchestration service for OCR, chunking, storage, embedding, and search
- `frontend-angular/` — Angular frontend for user interaction

## Purpose

The app layer integrates the backend pipeline and the frontend UI.

- `pipeline_service` exposes REST endpoints for document upload, review, indexing, and query.
- `frontend-angular` provides a web UI to call the pipeline service and display results.

For details on each service, see the README files inside `app/pipeline_service/` and `app/frontend-angular/`.
