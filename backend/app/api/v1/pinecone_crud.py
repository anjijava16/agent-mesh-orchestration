"""Pinecone Vector Database CRUD Operations Router.

Provides comprehensive vector operations for Pinecone:
- Index management (list, create, delete, describe)
- Vector operations (upsert, query, fetch, delete)
- Namespace management
- Metadata filtering
- Batch operations
- Index statistics
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pinecone import Pinecone, ServerlessSpec
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(
    prefix="/crud/pinecone",
    tags=["crud: pinecone"],
    dependencies=[Depends(current_user)],
)


def _get_pinecone_client() -> Pinecone:
    """Get Pinecone client."""
    return Pinecone(api_key=settings.pinecone_api_key)


class UpsertVectorsRequest(BaseModel):
    """Request to upsert vectors."""
    index_name: str = Field(description="Index name")
    vectors: list[dict[str, Any]] = Field(
        description="Vectors with id, values, and optional metadata"
    )
    namespace: str = Field(default="", description="Namespace (default: empty string)")


class QueryVectorsRequest(BaseModel):
    """Request to query vectors."""
    index_name: str = Field(description="Index name")
    vector: list[float] | None = Field(None, description="Query vector")
    vector_id: str | None = Field(None, description="Query by vector ID")
    top_k: int = Field(default=10, ge=1, le=10000, description="Number of results")
    namespace: str = Field(default="", description="Namespace")
    filter: dict[str, Any] = Field(default_factory=dict, description="Metadata filter")
    include_values: bool = Field(default=False, description="Include vector values")
    include_metadata: bool = Field(default=True, description="Include metadata")


class FetchVectorsRequest(BaseModel):
    """Request to fetch vectors by IDs."""
    index_name: str = Field(description="Index name")
    ids: list[str] = Field(description="Vector IDs to fetch")
    namespace: str = Field(default="", description="Namespace")


class DeleteVectorsRequest(BaseModel):
    """Request to delete vectors."""
    index_name: str = Field(description="Index name")
    ids: list[str] | None = Field(None, description="Vector IDs to delete")
    delete_all: bool = Field(default=False, description="Delete all vectors in namespace")
    namespace: str = Field(default="", description="Namespace")
    filter: dict[str, Any] = Field(default_factory=dict, description="Delete by metadata filter")


class CreateIndexRequest(BaseModel):
    """Request to create an index."""
    name: str = Field(description="Index name")
    dimension: int = Field(description="Vector dimension", ge=1, le=20000)
    metric: str = Field(default="cosine", description="Distance metric: cosine, euclidean, or dotproduct")
    cloud: str = Field(default="aws", description="Cloud provider")
    region: str = Field(default="us-east-1", description="Cloud region")


@router.get("/health", summary="Check Pinecone connection")
async def check_health() -> dict[str, Any]:
    """Check if Pinecone API is accessible."""
    try:
        pc = _get_pinecone_client()
        indexes = pc.list_indexes()
        
        return {
            "status": "healthy",
            "indexes_count": len(indexes.names())
        }
    
    except Exception as exc:
        return {
            "status": "unhealthy",
            "error": str(exc)
        }


@router.get("/indexes", summary="List all indexes")
async def list_indexes() -> dict[str, Any]:
    """List all Pinecone indexes."""
    try:
        pc = _get_pinecone_client()
        indexes = pc.list_indexes()
        
        index_list = []
        for idx in indexes:
            index_list.append({
                "name": idx.name,
                "dimension": idx.dimension,
                "metric": idx.metric,
                "host": idx.host,
                "status": idx.status.get("state") if idx.status else "unknown"
            })
        
        log.info("list_indexes", count=len(index_list))
        
        return {
            "indexes": index_list,
            "count": len(index_list)
        }
    
    except Exception as exc:
        log.error("list_indexes_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Pinecone error: {exc}")


@router.post("/indexes/create", summary="Create a new index")
async def create_index(request: CreateIndexRequest) -> dict[str, Any]:
    """Create a new Pinecone index."""
    try:
        pc = _get_pinecone_client()
        
        # Create serverless spec
        spec = ServerlessSpec(
            cloud=request.cloud,
            region=request.region
        )
        
        pc.create_index(
            name=request.name,
            dimension=request.dimension,
            metric=request.metric,
            spec=spec
        )
        
        log.info("create_index", 
                name=request.name,
                dimension=request.dimension,
                metric=request.metric)
        
        return {
            "created": True,
            "name": request.name,
            "dimension": request.dimension,
            "metric": request.metric,
            "note": "Index creation started. It may take a few moments to be ready."
        }
    
    except Exception as exc:
        log.error("create_index_error", name=request.name, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Pinecone error: {exc}")


@router.get("/indexes/{index_name}", summary="Describe an index")
async def describe_index(index_name: str) -> dict[str, Any]:
    """Get detailed information about an index."""
    try:
        pc = _get_pinecone_client()
        index_info = pc.describe_index(index_name)
        
        return {
            "name": index_info.name,
            "dimension": index_info.dimension,
            "metric": index_info.metric,
            "host": index_info.host,
            "status": index_info.status,
            "spec": index_info.spec
        }
    
    except Exception as exc:
        log.error("describe_index_error", index_name=index_name, error=str(exc))
        raise HTTPException(status_code=404, detail=f"Index not found: {exc}")


@router.delete("/indexes/{index_name}", summary="Delete an index")
async def delete_index(index_name: str) -> dict[str, Any]:
    """Delete a Pinecone index."""
    try:
        pc = _get_pinecone_client()
        pc.delete_index(index_name)
        
        log.warning("delete_index", index_name=index_name)
        
        return {
            "deleted": True,
            "index_name": index_name
        }
    
    except Exception as exc:
        log.error("delete_index_error", index_name=index_name, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Pinecone error: {exc}")


@router.get("/indexes/{index_name}/stats", summary="Get index statistics")
async def get_index_stats(
    index_name: str,
    namespace: str = Query(default="", description="Namespace to get stats for")
) -> dict[str, Any]:
    """Get statistics for an index."""
    try:
        pc = _get_pinecone_client()
        index = pc.Index(index_name)
        
        if namespace:
            stats = index.describe_index_stats(filter={"namespace": namespace})
        else:
            stats = index.describe_index_stats()
        
        return {
            "index_name": index_name,
            "dimension": stats.get("dimension"),
            "index_fullness": stats.get("index_fullness", 0),
            "total_vector_count": stats.get("total_vector_count", 0),
            "namespaces": stats.get("namespaces", {})
        }
    
    except Exception as exc:
        log.error("get_index_stats_error", index_name=index_name, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Pinecone error: {exc}")


@router.post("/vectors/upsert", summary="Upsert vectors")
async def upsert_vectors(request: UpsertVectorsRequest) -> dict[str, Any]:
    """Insert or update vectors in an index."""
    try:
        pc = _get_pinecone_client()
        index = pc.Index(request.index_name)
        
        # Prepare vectors for upsert
        vectors_data = []
        for vec in request.vectors:
            vectors_data.append({
                "id": vec.get("id"),
                "values": vec.get("values"),
                "metadata": vec.get("metadata", {})
            })
        
        result = index.upsert(
            vectors=vectors_data,
            namespace=request.namespace
        )
        
        log.info("upsert_vectors", 
                index=request.index_name,
                count=result.get("upserted_count", 0),
                namespace=request.namespace)
        
        return {
            "upserted": True,
            "upserted_count": result.get("upserted_count", 0),
            "index_name": request.index_name,
            "namespace": request.namespace
        }
    
    except Exception as exc:
        log.error("upsert_vectors_error", index=request.index_name, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Pinecone error: {exc}")


@router.post("/vectors/query", summary="Query vectors")
async def query_vectors(request: QueryVectorsRequest) -> dict[str, Any]:
    """Query for similar vectors."""
    try:
        pc = _get_pinecone_client()
        index = pc.Index(request.index_name)
        
        # Build query params
        query_params: dict[str, Any] = {
            "top_k": request.top_k,
            "namespace": request.namespace,
            "include_values": request.include_values,
            "include_metadata": request.include_metadata
        }
        
        if request.vector:
            query_params["vector"] = request.vector
        elif request.vector_id:
            query_params["id"] = request.vector_id
        else:
            raise HTTPException(
                status_code=400,
                detail="Either vector or vector_id must be provided"
            )
        
        if request.filter:
            query_params["filter"] = request.filter
        
        result = index.query(**query_params)
        
        matches = []
        for match in result.get("matches", []):
            matches.append({
                "id": match.get("id"),
                "score": match.get("score"),
                "values": match.get("values") if request.include_values else None,
                "metadata": match.get("metadata") if request.include_metadata else None
            })
        
        log.info("query_vectors", 
                index=request.index_name,
                matches=len(matches),
                namespace=request.namespace)
        
        return {
            "matches": matches,
            "count": len(matches),
            "namespace": request.namespace
        }
    
    except HTTPException:
        raise
    except Exception as exc:
        log.error("query_vectors_error", index=request.index_name, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Pinecone error: {exc}")


@router.post("/vectors/fetch", summary="Fetch vectors by IDs")
async def fetch_vectors(request: FetchVectorsRequest) -> dict[str, Any]:
    """Fetch vectors by their IDs."""
    try:
        pc = _get_pinecone_client()
        index = pc.Index(request.index_name)
        
        result = index.fetch(
            ids=request.ids,
            namespace=request.namespace
        )
        
        vectors = {}
        for vec_id, vec_data in result.get("vectors", {}).items():
            vectors[vec_id] = {
                "id": vec_id,
                "values": vec_data.get("values"),
                "metadata": vec_data.get("metadata", {})
            }
        
        log.info("fetch_vectors", 
                index=request.index_name,
                requested=len(request.ids),
                found=len(vectors),
                namespace=request.namespace)
        
        return {
            "vectors": vectors,
            "count": len(vectors),
            "namespace": request.namespace
        }
    
    except Exception as exc:
        log.error("fetch_vectors_error", index=request.index_name, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Pinecone error: {exc}")


@router.delete("/vectors/delete", summary="Delete vectors")
async def delete_vectors(request: DeleteVectorsRequest) -> dict[str, Any]:
    """Delete vectors from an index."""
    try:
        pc = _get_pinecone_client()
        index = pc.Index(request.index_name)
        
        if request.delete_all:
            # Delete all vectors in namespace
            index.delete(delete_all=True, namespace=request.namespace)
            log.warning("delete_all_vectors", 
                       index=request.index_name,
                       namespace=request.namespace)
            return {
                "deleted": True,
                "deleted_all": True,
                "namespace": request.namespace
            }
        
        elif request.ids:
            # Delete specific IDs
            index.delete(ids=request.ids, namespace=request.namespace)
            log.info("delete_vectors_by_ids", 
                    index=request.index_name,
                    count=len(request.ids),
                    namespace=request.namespace)
            return {
                "deleted": True,
                "count": len(request.ids),
                "namespace": request.namespace
            }
        
        elif request.filter:
            # Delete by metadata filter
            index.delete(filter=request.filter, namespace=request.namespace)
            log.info("delete_vectors_by_filter", 
                    index=request.index_name,
                    namespace=request.namespace)
            return {
                "deleted": True,
                "by_filter": True,
                "namespace": request.namespace
            }
        
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide ids, delete_all=True, or filter"
            )
    
    except HTTPException:
        raise
    except Exception as exc:
        log.error("delete_vectors_error", index=request.index_name, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Pinecone error: {exc}")


@router.post("/vectors/update", summary="Update vector metadata")
async def update_vector_metadata(
    index_name: str = Query(description="Index name"),
    vector_id: str = Query(description="Vector ID"),
    metadata: dict[str, Any] = Query(description="New metadata"),
    namespace: str = Query(default="", description="Namespace")
) -> dict[str, Any]:
    """Update the metadata of a specific vector."""
    try:
        pc = _get_pinecone_client()
        index = pc.Index(index_name)
        
        index.update(
            id=vector_id,
            set_metadata=metadata,
            namespace=namespace
        )
        
        log.info("update_vector_metadata", 
                index=index_name,
                vector_id=vector_id,
                namespace=namespace)
        
        return {
            "updated": True,
            "vector_id": vector_id,
            "namespace": namespace
        }
    
    except Exception as exc:
        log.error("update_vector_metadata_error", 
                 index=index_name,
                 vector_id=vector_id,
                 error=str(exc))
        raise HTTPException(status_code=500, detail=f"Pinecone error: {exc}")


@router.get("/indexes/{index_name}/namespaces", summary="List namespaces")
async def list_namespaces(index_name: str) -> dict[str, Any]:
    """List all namespaces in an index."""
    try:
        pc = _get_pinecone_client()
        index = pc.Index(index_name)
        
        stats = index.describe_index_stats()
        namespaces = stats.get("namespaces", {})
        
        namespace_list = []
        for ns_name, ns_data in namespaces.items():
            namespace_list.append({
                "name": ns_name,
                "vector_count": ns_data.get("vector_count", 0)
            })
        
        return {
            "index_name": index_name,
            "namespaces": namespace_list,
            "count": len(namespace_list)
        }
    
    except Exception as exc:
        log.error("list_namespaces_error", index_name=index_name, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Pinecone error: {exc}")


@router.get("/config", summary="Get Pinecone configuration")
async def get_config() -> dict[str, Any]:
    """Get Pinecone client configuration."""
    return {
        "api_key_configured": bool(settings.pinecone_api_key),
        "environment": settings.pinecone_environment if hasattr(settings, 'pinecone_environment') else "serverless",
        "features": {
            "serverless": True,
            "pod_based": False,
            "sparse_vectors": True,
            "metadata_filtering": True
        }
    }
