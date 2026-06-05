"""
opensearch_client.py — OpenSearch integration
==============================================
Two functions used by embedder.py:

    index_doc(docs)
        Index a list of embedded documents one by one.
        Called after index_chunks() finishes embedding.

    hybrid_search(query_vector, query_text, top_k)
        Send a hybrid query (BM25 + kNN) through the hybrid-pipeline.
        Returns top-k hits ready for candidates_from_hits().

Both functions read all settings from config/config.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import requests

# Ensure config/ is resolvable whether imported from its own dir or from app/
_SERVICE_DIR = Path(__file__).parent
_CONFIG_DIR  = _SERVICE_DIR / "config"

# Dynamically import config module to ensure we get embendding_service config
# Load directly from config.py to avoid relative import issues
_config_module_name = "__embedding_config__"
if _config_module_name not in sys.modules:
    _config_py_path = _CONFIG_DIR / "config.py"
    _config_spec = importlib.util.spec_from_file_location(_config_module_name, _config_py_path)
    _config_mod = importlib.util.module_from_spec(_config_spec)
    _config_mod.__file__ = str(_config_py_path)
    sys.modules[_config_module_name] = _config_mod
    _config_spec.loader.exec_module(_config_mod)
else:
    _config_mod = sys.modules[_config_module_name]

INDEX_NAME = _config_mod.INDEX_NAME
KNN_TOP_K = _config_mod.KNN_TOP_K
OPENSEARCH_URL = _config_mod.OPENSEARCH_URL
PIPELINE_NAME = _config_mod.PIPELINE_NAME

_HEADERS = {"Content-Type": "application/json"}

# Embedding dimension for Qwen3-Embedding-0.6B
EMBEDDING_DIM = 1024


# ---------------------------------------------------------------------------
# Index Initialization — ensure index exists with proper knn_vector mapping
# ---------------------------------------------------------------------------

def _ensure_index_exists() -> None:
    """
    Create the OpenSearch index if it doesn't exist, with proper mapping
    that defines 'embedding' as a knn_vector field for hybrid search.
    
    If the index exists but has an incorrect mapping (e.g., 'embedding' is not
    knn_vector type), it will be deleted and recreated with the correct mapping.
    
    This is called once at module import time to ensure the index is ready
    for documents and hybrid searches.
    """
    index_url = f"{OPENSEARCH_URL}/{INDEX_NAME}"
    
    try:
        # Check if index exists
        r = requests.head(index_url, headers=_HEADERS, timeout=10)
        if r.status_code == 200:
            # Index exists — check if mapping is correct
            try:
                r_mapping = requests.get(
                    f"{index_url}/_mapping",
                    headers=_HEADERS,
                    timeout=10,
                )
                if r_mapping.status_code == 200:
                    mappings = r_mapping.json()
                    # Check if embedding field is knn_vector type
                    embedding_type = mappings.get(INDEX_NAME, {}).get("mappings", {}).get("properties", {}).get("embedding", {}).get("type")
                    if embedding_type == "knn_vector":
                        return  # Mapping is correct, index is ready
                    else:
                        # Mapping is wrong, delete and recreate
                        print(f"[_ensure_index_exists] Detected incorrect embedding field type: {embedding_type}")
                        print(f"[_ensure_index_exists] Deleting index {INDEX_NAME} and recreating with correct mapping...")
                        r_delete = requests.delete(index_url, headers=_HEADERS, timeout=10)
                        if r_delete.status_code not in (200, 404):
                            print(f"[_ensure_index_exists] WARNING: Failed to delete index — status={r_delete.status_code}")
                            return
            except Exception as e:
                print(f"[_ensure_index_exists] WARNING: Could not check mapping — {e}")
                return
    except Exception:
        pass  # Assume it doesn't exist, try to create it
    
    # Create index with proper mapping for knn_vector
    mapping = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "knn": True,  # Enable KNN on this index
            }
        },
        "mappings": {
            "properties": {
                "chunk_id": {
                    "type": "keyword"
                },
                "text": {
                    "type": "text"
                },
                "embedding": {
                    "type": "knn_vector",
                    "dimension": EMBEDDING_DIM,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                        "parameters": {
                            "ef_construction": 512,
                            "m": 16,
                        }
                    }
                }
            }
        }
    }
    
    try:
        r = requests.put(
            index_url,
            json=mapping,
            headers=_HEADERS,
            timeout=30,
        )
        if r.status_code not in (200, 201):
            print(f"[_ensure_index_exists] WARNING: Failed to create index — status={r.status_code}")
            print(f"  {r.text[:300]}")
        else:
            print(f"[_ensure_index_exists] Successfully created index {INDEX_NAME} with knn_vector mapping")
    except Exception as e:
        print(f"[_ensure_index_exists] WARNING: Could not ensure index exists — {e}")


def _ensure_pipeline_exists() -> None:
    """
    Ensure the hybrid-pipeline exists in OpenSearch for hybrid search combining
    keyword and neural search results.
    """
    pipeline_url = f"{OPENSEARCH_URL}/_search/pipeline/{PIPELINE_NAME}"
    try:
        r = requests.get(pipeline_url, headers=_HEADERS, timeout=10)
        if r.status_code == 200:
            return  # Pipeline exists
    except Exception:
        pass
        
    pipeline_config = {
        "description": "Post processor for hybrid search",
        "phase_results_processors": [
            {
                "normalization-processor": {
                    "normalization": {
                        "technique": "min_max"
                    },
                    "combination": {
                        "technique": "arithmetic_mean",
                        "parameters": {
                            "weights": [0.3, 0.7]
                        }
                    }
                }
            }
        ]
    }
    
    try:
        r = requests.put(pipeline_url, json=pipeline_config, headers=_HEADERS, timeout=10)
        if r.status_code in (200, 201):
            print(f"[_ensure_pipeline_exists] Successfully created search pipeline {PIPELINE_NAME}")
        else:
            print(f"[_ensure_pipeline_exists] WARNING: Failed to create pipeline — status={r.status_code}")
            print(f"  {r.text[:300]}")
    except Exception as e:
        print(f"[_ensure_pipeline_exists] WARNING: Could not ensure pipeline exists — {e}")


# Call at module import time
_ensure_index_exists()
_ensure_pipeline_exists()


# ---------------------------------------------------------------------------
# Function 1 — index_doc
# ---------------------------------------------------------------------------

def index_doc(docs: list[dict[str, Any]]) -> int:
    """
    Index a list of embedded documents into OpenSearch one by one.

    Each document must have the shape produced by index_chunks():
        {
            "_id":       str,          ← becomes the OpenSearch document _id
            "text":      str,          ← stored for BM25 + reranker retrieval
            "embedding": list[float]   ← stored as knn_vector
        }

    chunk_id is stored both as the document _id AND inside _source
    so it is always available when a hit is returned, regardless of
    how _source filtering is configured on the search request.

    Returns
    -------
    int — number of documents successfully indexed
    """
    if not docs:
        return 0

    indexed = 0
    errors  = 0

    for doc in docs:
        chunk_id = doc["_id"]
        body = {
            "chunk_id":  chunk_id,       # stored in _source for explicit retrieval
            "text":      doc["text"],
            "embedding": doc["embedding"],
        }

        r = requests.put(
            f"{OPENSEARCH_URL}/{INDEX_NAME}/_doc/{chunk_id}",
            json=body,
            headers=_HEADERS,
            timeout=30,
        )
        if r.status_code in (200, 201):
            indexed += 1
        else:
            errors += 1
            print(f"[index_doc] ERROR chunk_id={chunk_id}  status={r.status_code}  {r.text[:200]}")

    if errors:
        print(f"[index_doc] indexed={indexed}  errors={errors}  total={len(docs)}")

    return indexed


# ---------------------------------------------------------------------------
# Function 2 — hybrid_search
# ---------------------------------------------------------------------------

def hybrid_search(
    query_vector: list[float],
    query_text:   str,
    top_k:        int = KNN_TOP_K,
) -> list[dict[str, Any]]:
    """
    Run a hybrid BM25 + kNN search through the configured pipeline.

    The pipeline (hybrid-pipeline) must already be created in OpenSearch
    Dashboard with arithmetic_mean combination before calling this function.

    Returns
    -------
    List of OpenSearch hits:
        [
            {
                "_id":    "chunk_id",           ← always present
                "_score": 0.91,
                "_source": {
                    "chunk_id": "chunk_id",     ← also in _source explicitly
                    "text":     "..."
                }
            },
            ...
        ]
    Ready to pass directly to reranker.candidates_from_hits().
    Use hit["_id"] or hit["_source"]["chunk_id"] to look up the original
    chunk JSON for page, bbox, block_ids, document_id, etc.
    """
    r = requests.post(
        f"{OPENSEARCH_URL}/{INDEX_NAME}/_search",
        json={
            "size": top_k,
            "query": {
                "hybrid": {
                    "queries": [
                        {
                            "match": {
                                "text": {"query": query_text}
                            }
                        },
                        {
                            "knn": {
                                "embedding": {
                                    "vector": query_vector,
                                    "k": top_k,
                                }
                            }
                        }
                    ]
                }
            },
            "_source": ["chunk_id", "text"],   # embedding excluded — not needed after indexing
        },
        params={"search_pipeline": PIPELINE_NAME},
        headers=_HEADERS,
        timeout=30,
    )

    if r.status_code != 200:
        raise RuntimeError(
            f"hybrid_search failed — status={r.status_code}  body={r.text[:300]}"
        )

    return r.json()["hits"]["hits"]