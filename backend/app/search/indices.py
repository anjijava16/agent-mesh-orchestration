"""Index definitions and bootstrap.

Two indices:
  * documents  - chunked file content for RAG. Hybrid: BM25 text + knn_vector.
  * memory     - long-term conversational memory (facts, summaries, decisions).

Both use the HNSW engine with cosine similarity. `index.knn` must be enabled at
creation time - you cannot turn it on later without a reindex.
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.core.logging import get_logger
from app.search.client import get_opensearch

log = get_logger(__name__)

ANALYSIS: dict[str, Any] = {
    "analyzer": {
        "agentmesh_text": {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["lowercase", "asciifolding", "english_possessive_stemmer", "english_stop", "english_stemmer"],
        }
    },
    "filter": {
        "english_stop": {"type": "stop", "stopwords": "_english_"},
        "english_stemmer": {"type": "stemmer", "language": "english"},
        "english_possessive_stemmer": {"type": "stemmer", "language": "possessive_english"},
    },
}


def _knn_field(dim: int) -> dict[str, Any]:
    return {
        "type": "knn_vector",
        "dimension": dim,
        "method": {
            "name": "hnsw",
            "space_type": "cosinesimil",
            "engine": "lucene",
            "parameters": {"ef_construction": 256, "m": 24},
        },
    }


def documents_mapping() -> dict[str, Any]:
    dim = settings.opensearch.embedding_dim
    return {
        "settings": {
            "index": {"knn": True, "knn.algo_param.ef_search": 128, "number_of_shards": 2, "number_of_replicas": 0},
            "analysis": ANALYSIS,
        },
        "mappings": {
            "properties": {
                "document_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "conversation_id": {"type": "keyword"},
                "filename": {"type": "keyword", "fields": {"text": {"type": "text", "analyzer": "agentmesh_text"}}},
                "title": {"type": "text", "analyzer": "agentmesh_text"},
                "content": {"type": "text", "analyzer": "agentmesh_text"},
                "embedding": _knn_field(dim),
                "page": {"type": "integer"},
                "chunk_index": {"type": "integer"},
                "token_count": {"type": "integer"},
                "content_type": {"type": "keyword"},
                "tags": {"type": "keyword"},
                "source_uri": {"type": "keyword"},
                "checksum": {"type": "keyword"},
                "created_at": {"type": "date"},
                "metadata": {"type": "object", "enabled": True},
            }
        },
    }


def memory_mapping() -> dict[str, Any]:
    dim = settings.opensearch.embedding_dim
    return {
        "settings": {
            "index": {"knn": True, "knn.algo_param.ef_search": 128, "number_of_shards": 1, "number_of_replicas": 0},
            "analysis": ANALYSIS,
        },
        "mappings": {
            "properties": {
                "memory_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "conversation_id": {"type": "keyword"},
                "kind": {"type": "keyword"},        # fact | preference | summary | decision | entity
                "content": {"type": "text", "analyzer": "agentmesh_text"},
                "embedding": _knn_field(dim),
                "importance": {"type": "float"},
                "framework": {"type": "keyword"},
                "source_message_id": {"type": "keyword"},
                "created_at": {"type": "date"},
                "last_accessed_at": {"type": "date"},
                "access_count": {"type": "integer"},
                "metadata": {"type": "object", "enabled": True},
            }
        },
    }


async def ensure_indices() -> None:
    client = get_opensearch()
    for name, body in (
        (settings.opensearch.documents_index, documents_mapping()),
        (settings.opensearch.memory_index, memory_mapping()),
    ):
        if not await client.indices.exists(index=name):
            await client.indices.create(index=name, body=body)
            log.info("opensearch_index_created", index=name)
        else:
            log.debug("opensearch_index_present", index=name)
