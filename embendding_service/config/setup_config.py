import sys
import time
import requests
import argparse

# Use relative import so it works when imported from outside the config folder
from config import (
    OPENSEARCH_URL,
    INDEX_NAME,
    PIPELINE_NAME,
    EMBEDDING_DIM
)

H = {"Content-Type": "application/json"}

# --------------------------------------------------
# 1. Check OpenSearch connection
# --------------------------------------------------
def check_connection():
    print("\n[1/4] Connecting to OpenSearch...")
    for i in range(10):
        try:
            r = requests.get(OPENSEARCH_URL, timeout=5)
            if r.status_code == 200:
                version = r.json()["version"]["number"]
                print(f"  ✔ Connected to OpenSearch {version}")
                return
        except requests.exceptions.RequestException:
            pass
        print(f"  retry {i+1}/10...")
        time.sleep(2)

    print("  ✘ Failed to connect")
    sys.exit(1)

# --------------------------------------------------
# 2. Create hybrid pipeline (Arithmetic Mean)
# --------------------------------------------------
def create_pipeline():
    print("\n[2/4] Creating pipeline...")
    url = f"{OPENSEARCH_URL}/_search/pipeline/{PIPELINE_NAME}"

    # delete if exists
    if requests.get(url, headers=H).status_code == 200:
        requests.delete(url, headers=H)
        print("  old pipeline deleted")

    # Using arithmetic_mean and min_max normalization
    payload = {
        "description": "Hybrid search (BM25 + kNN) using arithmetic mean",
        "phase_results_processors": [
            {
                "normalization-processor": {
                    "normalization": {
                        "technique": "min_max"
                    },
                    "combination": {
                        "technique": "arithmetic_mean",
                        "parameters": {
                            "weights": [0.5, 0.5]
                        }
                    }
                }
            }
        ]
    }

    r = requests.put(url, json=payload, headers=H)
    if r.status_code in (200, 201):
        print("  ✔ pipeline created")
    else:
        print("  ✘ pipeline failed")
        print(r.text)
        sys.exit(1)

# --------------------------------------------------
# 3. Create index
# --------------------------------------------------
def create_index(reset=False):
    print("\n[3/4] Creating index...")
    url = f"{OPENSEARCH_URL}/{INDEX_NAME}"

    if requests.get(url, headers=H).status_code == 200:
        if reset:
            requests.delete(url, headers=H)
            print("  old index deleted")
        else:
            print("  index already exists")
            return

    payload = {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 100
            }
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "text": {"type": "text"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": EMBEDDING_DIM,
                    "method": {
                        "name": "hnsw",
                        "engine": "lucene",
                        "space_type": "cosinesimil",
                        "parameters": {
                            "m": 16,
                            "ef_construction": 100
                        }
                    }
                }
            }
        }
    }

    r = requests.put(url, json=payload, headers=H)
    if r.status_code in (200, 201):
        print("  ✔ index created")
    else:
        print("  ✘ index failed")
        print(r.text)
        sys.exit(1)

# --------------------------------------------------
# 4. Test everything
# --------------------------------------------------
def test_pipeline():
    print("\n[4/4] Testing pipeline...")
    test_id = "test_doc"

    # index dummy doc
    requests.put(
        f"{OPENSEARCH_URL}/{INDEX_NAME}/_doc/{test_id}?refresh=true",
        json={
            "chunk_id": test_id,
            "text": "this is a hybrid search test document",
            "embedding": [0.0] * EMBEDDING_DIM
        },
        headers=H
    )

    # run hybrid query
    query = {
        "size": 1,
        "query": {
            "hybrid": {
                "queries": [
                    {"match": {"text": "hybrid test"}},
                    {"knn": {"embedding": {"vector": [0.0] * EMBEDDING_DIM, "k": 1}}}
                ]
            }
        }
    }

    r = requests.post(
        f"{OPENSEARCH_URL}/{INDEX_NAME}/_search",
        json=query,
        params={"search_pipeline": PIPELINE_NAME},
        headers=H
    )

    if r.status_code == 200:
        hits = r.json()["hits"]["hits"]
        if hits:
            print("  ✔ Hybrid search working")
            print(f"      score: {hits[0]['_score']}")
            print(f"      text : {hits[0]['_source']['text']}")
        else:
            print("  ⚠ No results returned")
    else:
        print("  ✘ search failed")
        print(r.text)

    # cleanup
    requests.delete(f"{OPENSEARCH_URL}/{INDEX_NAME}/_doc/{test_id}?refresh=true", headers=H)

# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Setup OpenSearch for document indexing")
    parser.add_argument("--reset", action="store_true", help="Force delete and recreate the index")
    args = parser.parse_args()
    
    check_connection()
    create_pipeline()
    create_index(reset=args.reset)
    test_pipeline()

    print("\n✅ EVERYTHING IS READY")
    print(f"Index   : {INDEX_NAME}")
    print(f"Pipeline: {PIPELINE_NAME}")
    print("You can now index and query safely 🚀")

if __name__ == "__main__":
    main()