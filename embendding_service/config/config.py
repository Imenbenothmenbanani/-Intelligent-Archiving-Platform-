"""
config/opensearch_config.py — OpenSearch settings
===================================================
All OpenSearch configuration in one place.
Sensitive values (host, port) are loaded from config/.env.
Everything else is defined here directly.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the config folder (same directory as this file)
_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

OPENSEARCH_HOST: str = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT: int = int(os.getenv("OPENSEARCH_PORT", "9200"))
OPENSEARCH_URL:  str = f"http://{OPENSEARCH_HOST}:{OPENSEARCH_PORT}"

# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

INDEX_NAME:     str = "index_doc"
EMBEDDING_DIM:  int = 1024          # Qwen3-Embedding-0.6B output dimension

# ---------------------------------------------------------------------------
# Search pipeline
# ---------------------------------------------------------------------------

PIPELINE_NAME:  str = "hybrid-pipeline"   # configured in OpenSearch Dashboard
KNN_TOP_K:      int = 50                  # candidates returned to the reranker