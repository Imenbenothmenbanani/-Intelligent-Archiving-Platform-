# config/__init__.py

# Export config variables
from .config import (
    OPENSEARCH_HOST,
    OPENSEARCH_PORT,
    OPENSEARCH_URL,
    INDEX_NAME,
    EMBEDDING_DIM,
    PIPELINE_NAME,
    KNN_TOP_K
)

# Export setup functions
from .setup_config import (
    check_connection,
    create_pipeline,
    create_index,
    test_pipeline,
    main as setup_opensearch
)

__all__ = [
    "OPENSEARCH_HOST",
    "OPENSEARCH_PORT",
    "OPENSEARCH_URL",
    "INDEX_NAME",
    "EMBEDDING_DIM",
    "PIPELINE_NAME",
    "KNN_TOP_K",
    "check_connection",
    "create_pipeline",
    "create_index",
    "test_pipeline",
    "setup_opensearch"
]