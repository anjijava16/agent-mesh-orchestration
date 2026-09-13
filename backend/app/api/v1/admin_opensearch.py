"""OpenSearch admin router (Enhanced).

Inspect indices, browse documents, run raw queries, and manage index lifecycle.
Enhanced with bulk operations, mapping updates, reindexing, and analytics.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.core.logging import get_logger
from app.search.client import get_opensearch

log = get_logger(__name__)
router = APIRouter(prefix="/admin/opensearch", tags=["admin-opensearch"])


class SearchBody(BaseModel):
    index: str
    query: dict[str, Any]
    size: int = 10


class IndexDocBody(BaseModel):
    doc: dict[str, Any]
    doc_id: str | None = None


class BulkIndexRequest(BaseModel):
    """Request to bulk index documents."""
    documents: list[dict[str, Any]] = Field(description="Documents to index")
    refresh: bool = Field(default=False, description="Refresh index after bulk operation")


class UpdateDocumentRequest(BaseModel):
    """Request to update a document."""
    doc: dict[str, Any] = Field(description="Partial document to merge")
    doc_as_upsert: bool = Field(default=False, description="Create if doesn't exist")


class CreateIndexRequest(BaseModel):
    """Request to create an index."""
    settings: dict[str, Any] = Field(default_factory=dict, description="Index settings")
    mappings: dict[str, Any] = Field(default_factory=dict, description="Index mappings")


class ReindexRequest(BaseModel):
    """Request to reindex from source to destination."""
    source_index: str = Field(description="Source index name")
    dest_index: str = Field(description="Destination index name")
    query: dict[str, Any] = Field(default_factory=dict, description="Optional query filter")


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



# ------------------------------------------------------------------ enhanced CRUD operations
@router.post("/indices/create/{index}", summary="Create a new index")
async def create_index(index: str, body: CreateIndexRequest) -> dict:
    """Create a new index with custom settings and mappings."""
    client = get_opensearch()
    
    try:
        body_dict = {}
        if body.settings:
            body_dict["settings"] = body.settings
        if body.mappings:
            body_dict["mappings"] = body.mappings
        
        result = await client.indices.create(index=index, body=body_dict if body_dict else None)
        
        log.info("create_index", index=index, acknowledged=result.get("acknowledged"))
        
        return {
            "acknowledged": result.get("acknowledged", False),
            "index": index,
            "shards_acknowledged": result.get("shards_acknowledged", False)
        }
    
    except Exception as exc:
        log.error("create_index_error", index=index, error=str(exc))
        raise HTTPException(status_code=400, detail=f"Failed to create index: {exc}")


@router.put("/indices/{index}/mapping", summary="Update index mapping")
async def update_mapping(index: str, mappings: dict[str, Any]) -> dict:
    """Update the mapping of an existing index."""
    client = get_opensearch()
    
    try:
        result = await client.indices.put_mapping(index=index, body=mappings)
        
        log.info("update_mapping", index=index, acknowledged=result.get("acknowledged"))
        
        return {
            "acknowledged": result.get("acknowledged", False),
            "index": index
        }
    
    except Exception as exc:
        log.error("update_mapping_error", index=index, error=str(exc))
        raise HTTPException(status_code=400, detail=f"Failed to update mapping: {exc}")


@router.post("/indices/{index}/docs/bulk", summary="Bulk index documents")
async def bulk_index_documents(index: str, body: BulkIndexRequest) -> dict:
    """Bulk index multiple documents at once."""
    client = get_opensearch()
    
    try:
        # Prepare bulk body
        bulk_body = []
        for doc in body.documents:
            bulk_body.append({"index": {"_index": index}})
            bulk_body.append(doc)
        
        result = await client.bulk(body=bulk_body, refresh=body.refresh)
        
        success_count = sum(1 for item in result["items"] if item["index"]["status"] in (200, 201))
        error_count = len(result["items"]) - success_count
        
        log.info("bulk_index", 
                index=index, 
                total=len(body.documents),
                success=success_count,
                errors=error_count)
        
        return {
            "indexed": success_count,
            "errors": error_count,
            "total": len(body.documents),
            "took_ms": result.get("took"),
            "items": result.get("items", []) if error_count > 0 else []
        }
    
    except Exception as exc:
        log.error("bulk_index_error", index=index, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Bulk indexing failed: {exc}")


@router.put("/indices/{index}/docs/{doc_id}", summary="Update a document")
async def update_document(index: str, doc_id: str, body: UpdateDocumentRequest) -> dict:
    """Update an existing document (partial update)."""
    client = get_opensearch()
    
    try:
        result = await client.update(
            index=index,
            id=doc_id,
            body={"doc": body.doc, "doc_as_upsert": body.doc_as_upsert}
        )
        
        log.info("update_document", index=index, doc_id=doc_id, result=result.get("result"))
        
        return {
            "_id": result["_id"],
            "result": result.get("result"),
            "_version": result.get("_version")
        }
    
    except Exception as exc:
        log.error("update_document_error", index=index, doc_id=doc_id, error=str(exc))
        raise HTTPException(status_code=404, detail=f"Failed to update document: {exc}")


@router.delete("/indices/{index}/docs", summary="Delete documents by query")
async def delete_by_query(index: str, query: dict[str, Any]) -> dict:
    """Delete all documents matching a query."""
    client = get_opensearch()
    
    try:
        result = await client.delete_by_query(
            index=index,
            body={"query": query}
        )
        
        log.warning("delete_by_query", 
                   index=index, 
                   deleted=result.get("deleted", 0),
                   total=result.get("total", 0))
        
        return {
            "deleted": result.get("deleted", 0),
            "total": result.get("total", 0),
            "took_ms": result.get("took"),
            "failures": result.get("failures", [])
        }
    
    except Exception as exc:
        log.error("delete_by_query_error", index=index, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Delete by query failed: {exc}")


@router.post("/indices/{index}/refresh", summary="Refresh an index")
async def refresh_index(index: str) -> dict:
    """Manually refresh an index to make recent changes visible."""
    client = get_opensearch()
    
    try:
        result = await client.indices.refresh(index=index)
        
        log.info("refresh_index", index=index)
        
        return {
            "refreshed": True,
            "index": index,
            "shards": result.get("_shards", {})
        }
    
    except Exception as exc:
        log.error("refresh_index_error", index=index, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Refresh failed: {exc}")


@router.post("/reindex", summary="Reindex from source to destination")
async def reindex(body: ReindexRequest) -> dict:
    """Reindex documents from one index to another."""
    client = get_opensearch()
    
    try:
        reindex_body: dict[str, Any] = {
            "source": {"index": body.source_index},
            "dest": {"index": body.dest_index}
        }
        
        if body.query:
            reindex_body["source"]["query"] = body.query
        
        result = await client.reindex(body=reindex_body, wait_for_completion=False)
        
        log.info("reindex", 
                source=body.source_index,
                dest=body.dest_index,
                task_id=result.get("task"))
        
        return {
            "started": True,
            "source_index": body.source_index,
            "dest_index": body.dest_index,
            "task_id": result.get("task"),
            "note": "Reindexing started. Check task status with task ID."
        }
    
    except Exception as exc:
        log.error("reindex_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Reindex failed: {exc}")


@router.get("/tasks/{task_id}", summary="Get task status")
async def get_task_status(task_id: str) -> dict:
    """Get the status of a long-running task (like reindexing)."""
    client = get_opensearch()
    
    try:
        result = await client.tasks.get(task_id=task_id)
        
        return {
            "task_id": task_id,
            "completed": result.get("completed", False),
            "task": result.get("task", {}),
            "response": result.get("response", {})
        }
    
    except Exception as exc:
        log.error("get_task_error", task_id=task_id, error=str(exc))
        raise HTTPException(status_code=404, detail=f"Task not found: {exc}")


@router.get("/indices/{index}/count", summary="Count documents in index")
async def count_documents(
    index: str,
    query: dict[str, Any] = Query(default_factory=dict, description="Optional query filter")
) -> dict:
    """Count documents in an index, optionally with a query filter."""
    client = get_opensearch()
    
    try:
        body = {"query": query} if query else None
        result = await client.count(index=index, body=body)
        
        return {
            "index": index,
            "count": result.get("count", 0)
        }
    
    except Exception as exc:
        log.error("count_documents_error", index=index, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Count failed: {exc}")


@router.post("/indices/{index}/analyze", summary="Analyze text")
async def analyze_text(
    index: str,
    text: str = Query(description="Text to analyze"),
    analyzer: str = Query(default="standard", description="Analyzer to use")
) -> dict:
    """Analyze text using an index's analyzer."""
    client = get_opensearch()
    
    try:
        result = await client.indices.analyze(
            index=index,
            body={"analyzer": analyzer, "text": text}
        )
        
        tokens = [token["token"] for token in result.get("tokens", [])]
        
        return {
            "index": index,
            "analyzer": analyzer,
            "tokens": tokens,
            "token_count": len(tokens),
            "details": result.get("tokens", [])
        }
    
    except Exception as exc:
        log.error("analyze_text_error", index=index, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")


@router.get("/indices/{index}/aliases", summary="Get index aliases")
async def get_aliases(index: str) -> dict:
    """Get all aliases for an index."""
    client = get_opensearch()
    
    try:
        result = await client.indices.get_alias(index=index)
        
        return {
            "index": index,
            "aliases": result.get(index, {}).get("aliases", {})
        }
    
    except Exception as exc:
        log.error("get_aliases_error", index=index, error=str(exc))
        raise HTTPException(status_code=404, detail=f"Failed to get aliases: {exc}")


@router.put("/indices/{index}/aliases/{alias}", summary="Add an alias")
async def add_alias(index: str, alias: str) -> dict:
    """Add an alias to an index."""
    client = get_opensearch()
    
    try:
        result = await client.indices.put_alias(index=index, name=alias)
        
        log.info("add_alias", index=index, alias=alias)
        
        return {
            "acknowledged": result.get("acknowledged", False),
            "index": index,
            "alias": alias
        }
    
    except Exception as exc:
        log.error("add_alias_error", index=index, alias=alias, error=str(exc))
        raise HTTPException(status_code=400, detail=f"Failed to add alias: {exc}")


@router.delete("/indices/{index}/aliases/{alias}", summary="Remove an alias")
async def remove_alias(index: str, alias: str) -> dict:
    """Remove an alias from an index."""
    client = get_opensearch()
    
    try:
        result = await client.indices.delete_alias(index=index, name=alias)
        
        log.info("remove_alias", index=index, alias=alias)
        
        return {
            "acknowledged": result.get("acknowledged", False),
            "index": index,
            "alias": alias
        }
    
    except Exception as exc:
        log.error("remove_alias_error", index=index, alias=alias, error=str(exc))
        raise HTTPException(status_code=404, detail=f"Failed to remove alias: {exc}")


@router.get("/indices/{index}/segments", summary="Get index segments info")
async def get_segments(index: str) -> dict:
    """Get segment information for an index."""
    client = get_opensearch()
    
    try:
        result = await client.indices.segments(index=index)
        
        idx_segments = result.get("indices", {}).get(index, {})
        
        return {
            "index": index,
            "segments": idx_segments
        }
    
    except Exception as exc:
        log.error("get_segments_error", index=index, error=str(exc))
        raise HTTPException(status_code=404, detail=f"Failed to get segments: {exc}")
