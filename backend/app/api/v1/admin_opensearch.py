"""OpenSearch admin router.

Inspect indices, browse documents, run raw queries, and manage index lifecycle.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.search.client import get_opensearch

router = APIRouter(prefix="/admin/opensearch", tags=["admin-opensearch"])


class SearchBody(BaseModel):
    index: str
    query: dict[str, Any]
    size: int = 10


class IndexDocBody(BaseModel):
    doc: dict[str, Any]
    doc_id: str | None = None


# ------------------------------------------------------------------ cluster
@router.get("/cluster")
async def cluster_info() -> dict:
    """Cluster health, node count, and version."""
    client = get_opensearch()
    health = await client.cluster.health()
    info = await client.info()
    return {
        "cluster_name": health.get("cluster_name"),
        "status": health.get("status"),
        "number_of_nodes": health.get("number_of_nodes"),
        "active_shards": health.get("active_shards"),
        "version": info.get("version", {}).get("number"),
    }


# ------------------------------------------------------------------ indices
@router.get("/indices")
async def list_indices() -> dict:
    """All indices with doc counts and sizes."""
    client = get_opensearch()
    cat = await client.cat.indices(format="json")
    indices = [
        {
            "name": idx.get("index"),
            "health": idx.get("health"),
            "status": idx.get("status"),
            "docs_count": idx.get("docs.count"),
            "store_size": idx.get("store.size"),
            "pri_shards": idx.get("pri"),
            "rep_shards": idx.get("rep"),
        }
        for idx in cat
        if not idx.get("index", "").startswith(".")
    ]
    return {"indices": indices, "total": len(indices)}


@router.get("/indices/{index}")
async def index_detail(index: str) -> dict:
    """Mapping and settings for an index."""
    client = get_opensearch()
    try:
        mapping = await client.indices.get_mapping(index=index)
        idx_settings = await client.indices.get_settings(index=index)
        stats = await client.indices.stats(index=index)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Index '{index}' not found: {exc}") from exc

    idx_stats = stats.get("indices", {}).get(index, {}).get("total", {})
    return {
        "index": index,
        "mapping": mapping.get(index, {}).get("mappings", {}),
        "settings": idx_settings.get(index, {}).get("settings", {}),
        "docs_count": idx_stats.get("docs", {}).get("count", 0),
        "store_size_bytes": idx_stats.get("store", {}).get("size_in_bytes", 0),
    }


@router.delete("/indices/{index}")
async def delete_index(index: str) -> dict:
    """Delete an index. Use with caution."""
    client = get_opensearch()
    result = await client.indices.delete(index=index, ignore=[400, 404])
    return {"acknowledged": result.get("acknowledged", False), "index": index}


# ------------------------------------------------------------------ documents
@router.get("/indices/{index}/docs")
async def list_documents(
    index: str,
    size: int = Query(20, ge=1, le=200),
    from_: int = Query(0, ge=0, alias="from"),
) -> dict:
    """Browse documents in an index."""
    client = get_opensearch()
    result = await client.search(
        index=index,
        body={"query": {"match_all": {}}, "size": size, "from": from_},
    )
    hits = result.get("hits", {})
    return {
        "index": index,
        "total": hits.get("total", {}).get("value", 0),
        "docs": [
            {"_id": h["_id"], "_score": h.get("_score"), **h.get("_source", {})}
            for h in hits.get("hits", [])
        ],
    }


@router.get("/indices/{index}/docs/{doc_id}")
async def get_document(index: str, doc_id: str) -> dict:
    """Get a single document by ID."""
    client = get_opensearch()
    try:
        result = await client.get(index=index, id=doc_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Document not found: {exc}") from exc
    return {"_id": result["_id"], "_version": result.get("_version"), **result.get("_source", {})}


@router.post("/indices/{index}/docs")
async def index_document(index: str, body: IndexDocBody) -> dict:
    """Index (create/update) a document."""
    client = get_opensearch()
    kwargs: dict[str, Any] = {"index": index, "body": body.doc}
    if body.doc_id:
        kwargs["id"] = body.doc_id
    result = await client.index(**kwargs)
    return {"_id": result["_id"], "result": result.get("result"), "_version": result.get("_version")}


@router.delete("/indices/{index}/docs/{doc_id}")
async def delete_document(index: str, doc_id: str) -> dict:
    """Delete a document by ID."""
    client = get_opensearch()
    result = await client.delete(index=index, id=doc_id, ignore=[404])
    return {"_id": doc_id, "result": result.get("result")}


# ------------------------------------------------------------------ search
@router.post("/search")
async def raw_search(body: SearchBody) -> dict:
    """Execute a raw OpenSearch query."""
    client = get_opensearch()
    result = await client.search(index=body.index, body=body.query, size=body.size)
    hits = result.get("hits", {})
    return {
        "total": hits.get("total", {}).get("value", 0),
        "max_score": hits.get("max_score"),
        "hits": [
            {"_id": h["_id"], "_score": h.get("_score"), **h.get("_source", {})}
            for h in hits.get("hits", [])
        ],
        "took_ms": result.get("took"),
    }


# ------------------------------------------------------------------ app indices
@router.get("/app-indices")
async def app_indices() -> dict:
    """Status of the two application indices."""
    client = get_opensearch()
    out = {}
    for name, idx in [
        ("documents", settings.opensearch.documents_index),
        ("memory", settings.opensearch.memory_index),
    ]:
        try:
            stats = await client.indices.stats(index=idx)
            idx_stats = stats.get("indices", {}).get(idx, {}).get("total", {})
            out[name] = {
                "index": idx,
                "docs_count": idx_stats.get("docs", {}).get("count", 0),
                "store_size_bytes": idx_stats.get("store", {}).get("size_in_bytes", 0),
                "status": "exists",
            }
        except Exception:
            out[name] = {"index": idx, "status": "missing"}
    return out
