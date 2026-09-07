"""MongoDB Atlas Vector Search client.

Provides the same retrieval capabilities as the OpenSearch backend — vector
search, text search, and hybrid fusion — using MongoDB's ``$vectorSearch``
and ``$search`` aggregation stages.

This module is only imported when ``VECTOR_BACKEND=mongodb``.  The interface
mirrors what ``hybrid.py`` and ``long_term.py`` need so the dispatch layer
in ``hybrid.py`` can call either backend transparently.

Local dev uses a single-node replica set (required for change streams and
``$vectorSearch``).  Production should point ``MONGODB_URI`` at Atlas.
"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import motor.motor_asyncio
import pymongo

from app.config import settings
from app.core.logging import get_logger
from app.core.resilience import with_resilience
from app.core.resilience import CircuitBreaker

log = get_logger(__name__)

MONGO_BREAKER = CircuitBreaker("mongodb")

_async_client: motor.motor_asyncio.AsyncIOMotorClient | None = None
_sync_client: pymongo.MongoClient | None = None


def get_mongo_async() -> motor.motor_asyncio.AsyncIOMotorDatabase:
    """Return the async MongoDB database handle (for the API server)."""
    global _async_client
    if _async_client is None:
        _async_client = motor.motor_asyncio.AsyncIOMotorClient(
            settings.mongodb.uri,
            serverSelectionTimeoutMS=settings.mongodb.timeout_ms,
        )
    return _async_client[settings.mongodb.database]


def get_mongo_sync() -> pymongo.database.Database:
    """Return a sync MongoDB database handle (for Celery workers)."""
    global _sync_client
    if _sync_client is None:
        _sync_client = pymongo.MongoClient(
            settings.mongodb.uri,
            serverSelectionTimeoutMS=settings.mongodb.timeout_ms,
        )
    return _sync_client[settings.mongodb.database]


async def close_mongo() -> None:
    global _async_client
    if _async_client is not None:
        _async_client.close()
        _async_client = None


# ---------------------------------------------------------------------------
# Index bootstrap
# ---------------------------------------------------------------------------

async def ensure_mongo_collections() -> None:
    """Create collections and Atlas Search indexes if they do not exist.

    On a local replica set (not Atlas), ``$vectorSearch`` requires a search
    index created via ``createSearchIndexes``.  This command is Atlas-only
    in older server versions, so we try and log a warning on failure rather
    than blocking startup.
    """
    db = get_mongo_async()
    existing = await db.list_collection_names()

    for coll_name in (settings.mongodb.documents_collection, settings.mongodb.memory_collection):
        if coll_name not in existing:
            await db.create_collection(coll_name)
            log.info("mongo_collection_created", collection=coll_name)

    # Ensure standard indexes for filtering.
    docs = db[settings.mongodb.documents_collection]
    await docs.create_index("document_id")
    await docs.create_index("user_id")
    await docs.create_index([("user_id", 1), ("document_id", 1)])

    mem = db[settings.mongodb.memory_collection]
    await mem.create_index("user_id")
    await mem.create_index("memory_id")

    # Attempt to create vector search indexes (Atlas-only command).
    for coll, index_name in [
        (docs, settings.mongodb.vector_index),
        (mem, settings.mongodb.vector_index),
    ]:
        try:
            await coll.create_search_index({
                "definition": {
                    "mappings": {
                        "dynamic": True,
                        "fields": {
                            "embedding": {
                                "type": "knnVector",
                                "dimensions": settings.mongodb.embedding_dim,
                                "similarity": "cosine",
                            }
                        },
                    }
                },
                "name": index_name,
            })
            log.info("mongo_vector_index_created", collection=coll.name, index=index_name)
        except Exception as exc:
            # Local mongod does not support createSearchIndexes — that is fine,
            # we fall back to in-memory cosine in _vector_search_fallback.
            log.debug("mongo_vector_index_skipped", collection=coll.name,
                      error=str(exc)[:200])


# ---------------------------------------------------------------------------
# Vector search
# ---------------------------------------------------------------------------

@with_resilience(breaker=MONGO_BREAKER, timeout=settings.resilience.search_timeout_seconds, label="mongo.vector")
async def mongo_vector_search(
    collection_name: str,
    vector: list[float],
    *,
    user_id: str | None = None,
    document_ids: Sequence[str] | None = None,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Run $vectorSearch (Atlas) with a fallback for local dev."""
    db = get_mongo_async()
    coll = db[collection_name]

    # Build pre-filter.
    pre_filter: dict[str, Any] = {}
    if user_id:
        pre_filter["user_id"] = user_id
    if document_ids:
        pre_filter["document_id"] = {"$in": list(document_ids)}

    try:
        # Atlas Vector Search pipeline.
        pipeline: list[dict[str, Any]] = [
            {
                "$vectorSearch": {
                    "index": settings.mongodb.vector_index,
                    "path": "embedding",
                    "queryVector": vector,
                    "numCandidates": top_k * 10,
                    "limit": top_k,
                    **({"filter": pre_filter} if pre_filter else {}),
                }
            },
            {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
            {"$project": {"embedding": 0}},
        ]
        results = await coll.aggregate(pipeline).to_list(length=top_k)
        if results:
            return results
    except Exception as exc:
        log.debug("mongo_atlas_vector_unavailable_using_fallback", error=str(exc)[:200])

    # Fallback: brute-force cosine for local dev without Atlas.
    return await _vector_search_fallback(coll, vector, user_id, document_ids, top_k)


async def _vector_search_fallback(
    coll: Any,
    vector: list[float],
    user_id: str | None,
    document_ids: Sequence[str] | None,
    top_k: int,
) -> list[dict[str, Any]]:
    """Brute-force cosine similarity when Atlas Search indexes are unavailable."""
    query: dict[str, Any] = {}
    if user_id:
        query["user_id"] = user_id
    if document_ids:
        query["document_id"] = {"$in": list(document_ids)}

    cursor = coll.find(query, {"embedding": 1, "content": 1, "document_id": 1,
                                "filename": 1, "page": 1, "chunk_id": 1,
                                "chunk_index": 1, "metadata": 1, "user_id": 1,
                                "kind": 1, "memory_id": 1, "importance": 1})
    docs = await cursor.to_list(length=5000)
    if not docs:
        return []

    import math

    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0

    scored = []
    for doc in docs:
        emb = doc.get("embedding")
        if not emb:
            continue
        score = _cosine(vector, emb)
        doc["score"] = score
        doc.pop("embedding", None)
        scored.append(doc)

    scored.sort(key=lambda d: d["score"], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------------------
# Text search (for hybrid fusion)
# ---------------------------------------------------------------------------

@with_resilience(breaker=MONGO_BREAKER, timeout=settings.resilience.search_timeout_seconds, label="mongo.text")
async def mongo_text_search(
    collection_name: str,
    query: str,
    *,
    user_id: str | None = None,
    document_ids: Sequence[str] | None = None,
    top_k: int = 50,
) -> list[dict[str, Any]]:
    """Text search using MongoDB's $text or $search operator."""
    db = get_mongo_async()
    coll = db[collection_name]

    match_filter: dict[str, Any] = {"$text": {"$search": query}}
    if user_id:
        match_filter["user_id"] = user_id
    if document_ids:
        match_filter["document_id"] = {"$in": list(document_ids)}

    try:
        cursor = coll.find(
            match_filter,
            {"score": {"$meta": "textScore"}, "embedding": 0},
        ).sort([("score", {"$meta": "textScore"})]).limit(top_k)
        return await cursor.to_list(length=top_k)
    except Exception:
        # If no text index exists, fall back to regex.
        regex_filter: dict[str, Any] = {"content": {"$regex": query, "$options": "i"}}
        if user_id:
            regex_filter["user_id"] = user_id
        if document_ids:
            regex_filter["document_id"] = {"$in": list(document_ids)}
        cursor = coll.find(regex_filter, {"embedding": 0}).limit(top_k)
        results = await cursor.to_list(length=top_k)
        for i, doc in enumerate(results):
            doc["score"] = 1.0 / (i + 1)
        return results


# ---------------------------------------------------------------------------
# Write operations (used by ingestion and long-term memory)
# ---------------------------------------------------------------------------

async def mongo_index_document(collection_name: str, doc_id: str, body: dict[str, Any]) -> None:
    """Upsert a document (chunk or memory) into MongoDB."""
    db = get_mongo_async()
    await db[collection_name].replace_one(
        {"_id": doc_id}, {**body, "_id": doc_id}, upsert=True,
    )


def mongo_bulk_index_sync(collection_name: str, documents: list[dict[str, Any]]) -> tuple[int, int]:
    """Bulk upsert for Celery workers (sync). Returns (success_count, error_count)."""
    db = get_mongo_sync()
    coll = db[collection_name]
    ops = [
        pymongo.ReplaceOne({"_id": doc["_id"]}, doc, upsert=True)
        for doc in documents
    ]
    try:
        result = coll.bulk_write(ops, ordered=False)
        return result.upserted_count + result.modified_count, 0
    except pymongo.errors.BulkWriteError as exc:
        details = exc.details
        ok = details.get("nUpserted", 0) + details.get("nModified", 0)
        errs = len(details.get("writeErrors", []))
        return ok, errs


async def mongo_delete_by_document(collection_name: str, document_id: str) -> int:
    """Delete all chunks for a document. Returns delete count."""
    db = get_mongo_async()
    result = await db[collection_name].delete_many({"document_id": document_id})
    return result.deleted_count


async def mongo_delete_by_filter(collection_name: str, filter_dict: dict[str, Any]) -> int:
    """Delete by arbitrary filter (used by long-term memory forget)."""
    db = get_mongo_async()
    result = await db[collection_name].delete_many(filter_dict)
    return result.deleted_count
