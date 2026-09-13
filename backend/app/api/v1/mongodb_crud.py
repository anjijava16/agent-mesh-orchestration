"""MongoDB CRUD Operations Router.

Provides comprehensive CRUD operations for MongoDB:
- Database management (list, create, drop)
- Collection management (list, create, drop, stats)
- Document operations (insert, find, update, delete - single and bulk)
- Index management
- Aggregation pipelines
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError

from app.api.deps import current_user
from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(
    prefix="/crud/mongodb",
    tags=["crud: mongodb"],
    dependencies=[Depends(current_user)],
)


def _get_mongo_client() -> AsyncIOMotorClient:
    """Get MongoDB async client."""
    return AsyncIOMotorClient(
        host=settings.mongodb_host,
        port=settings.mongodb_port,
        username=settings.mongodb_user,
        password=settings.mongodb_password,
    )


class InsertDocumentRequest(BaseModel):
    """Request to insert a document."""
    database: str = Field(description="Database name")
    collection: str = Field(description="Collection name")
    document: dict[str, Any] = Field(description="Document to insert")


class InsertManyRequest(BaseModel):
    """Request to insert multiple documents."""
    database: str
    collection: str
    documents: list[dict[str, Any]] = Field(description="Documents to insert")


class FindDocumentsRequest(BaseModel):
    """Request to find documents."""
    database: str
    collection: str
    filter: dict[str, Any] = Field(default_factory=dict, description="Query filter")
    projection: dict[str, Any] | None = Field(None, description="Fields to return")
    limit: int = Field(default=100, ge=1, le=1000, description="Max documents to return")
    skip: int = Field(default=0, ge=0, description="Number of documents to skip")
    sort: list[tuple[str, int]] | None = Field(None, description="Sort specification")


class UpdateDocumentRequest(BaseModel):
    """Request to update documents."""
    database: str
    collection: str
    filter: dict[str, Any] = Field(description="Query filter")
    update: dict[str, Any] = Field(description="Update operations")
    upsert: bool = Field(default=False, description="Insert if not found")


class DeleteDocumentRequest(BaseModel):
    """Request to delete documents."""
    database: str
    collection: str
    filter: dict[str, Any] = Field(description="Query filter")


class AggregationRequest(BaseModel):
    """Request to run aggregation pipeline."""
    database: str
    collection: str
    pipeline: list[dict[str, Any]] = Field(description="Aggregation pipeline stages")


class CreateIndexRequest(BaseModel):
    """Request to create an index."""
    database: str
    collection: str
    keys: dict[str, int] = Field(description="Index keys (field: 1 or -1)")
    unique: bool = Field(default=False, description="Unique index")
    name: str | None = Field(None, description="Index name")


@router.get("/databases", summary="List all databases")
async def list_databases() -> dict[str, Any]:
    """List all MongoDB databases."""
    try:
        client = _get_mongo_client()
        databases = await client.list_database_names()
        
        db_info = []
        for db_name in databases:
            db = client[db_name]
            stats = await db.command("dbStats")
            db_info.append({
                "name": db_name,
                "collections": stats.get("collections", 0),
                "data_size": stats.get("dataSize", 0),
                "storage_size": stats.get("storageSize", 0)
            })
        
        client.close()
        
        log.info("list_databases", count=len(databases))
        
        return {
            "databases": db_info,
            "count": len(databases)
        }
    
    except PyMongoError as exc:
        log.error("list_databases_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.get("/databases/{database}/collections", summary="List collections in database")
async def list_collections(database: str) -> dict[str, Any]:
    """List all collections in a database."""
    try:
        client = _get_mongo_client()
        db = client[database]
        collections = await db.list_collection_names()
        
        coll_info = []
        for coll_name in collections:
            coll = db[coll_name]
            count = await coll.count_documents({})
            coll_info.append({
                "name": coll_name,
                "document_count": count
            })
        
        client.close()
        
        log.info("list_collections", database=database, count=len(collections))
        
        return {
            "database": database,
            "collections": coll_info,
            "count": len(collections)
        }
    
    except PyMongoError as exc:
        log.error("list_collections_error", database=database, error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.post("/collections/create", summary="Create a collection")
async def create_collection(
    database: str = Query(description="Database name"),
    collection: str = Query(description="Collection name")
) -> dict[str, Any]:
    """Create a new collection."""
    try:
        client = _get_mongo_client()
        db = client[database]
        await db.create_collection(collection)
        
        client.close()
        
        log.info("create_collection", database=database, collection=collection)
        
        return {
            "created": True,
            "database": database,
            "collection": collection
        }
    
    except PyMongoError as exc:
        log.error("create_collection_error", database=database, collection=collection, error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.delete("/collections/drop", summary="Drop a collection")
async def drop_collection(
    database: str = Query(description="Database name"),
    collection: str = Query(description="Collection name")
) -> dict[str, Any]:
    """Drop (delete) a collection."""
    try:
        client = _get_mongo_client()
        db = client[database]
        await db.drop_collection(collection)
        
        client.close()
        
        log.warning("drop_collection", database=database, collection=collection)
        
        return {
            "dropped": True,
            "database": database,
            "collection": collection
        }
    
    except PyMongoError as exc:
        log.error("drop_collection_error", database=database, collection=collection, error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.post("/documents/insert", summary="Insert a document")
async def insert_document(request: InsertDocumentRequest) -> dict[str, Any]:
    """Insert a single document into a collection."""
    try:
        client = _get_mongo_client()
        db = client[request.database]
        collection = db[request.collection]
        
        result = await collection.insert_one(request.document)
        
        client.close()
        
        log.info("insert_document", 
                database=request.database, 
                collection=request.collection,
                inserted_id=str(result.inserted_id))
        
        return {
            "inserted": True,
            "inserted_id": str(result.inserted_id),
            "database": request.database,
            "collection": request.collection
        }
    
    except PyMongoError as exc:
        log.error("insert_document_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.post("/documents/insert_many", summary="Insert multiple documents")
async def insert_many_documents(request: InsertManyRequest) -> dict[str, Any]:
    """Insert multiple documents into a collection."""
    try:
        client = _get_mongo_client()
        db = client[request.database]
        collection = db[request.collection]
        
        result = await collection.insert_many(request.documents)
        
        client.close()
        
        log.info("insert_many_documents", 
                database=request.database, 
                collection=request.collection,
                count=len(result.inserted_ids))
        
        return {
            "inserted": True,
            "inserted_count": len(result.inserted_ids),
            "inserted_ids": [str(id) for id in result.inserted_ids],
            "database": request.database,
            "collection": request.collection
        }
    
    except PyMongoError as exc:
        log.error("insert_many_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.post("/documents/find", summary="Find documents")
async def find_documents(request: FindDocumentsRequest) -> dict[str, Any]:
    """Find documents in a collection with filters."""
    try:
        client = _get_mongo_client()
        db = client[request.database]
        collection = db[request.collection]
        
        cursor = collection.find(
            filter=request.filter,
            projection=request.projection,
            limit=request.limit,
            skip=request.skip
        )
        
        if request.sort:
            cursor = cursor.sort(request.sort)
        
        documents = await cursor.to_list(length=request.limit)
        
        # Convert ObjectId to string
        for doc in documents:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
        
        total_count = await collection.count_documents(request.filter)
        
        client.close()
        
        log.info("find_documents", 
                database=request.database, 
                collection=request.collection,
                returned=len(documents),
                total=total_count)
        
        return {
            "documents": documents,
            "count": len(documents),
            "total_count": total_count,
            "has_more": total_count > (request.skip + len(documents)),
            "database": request.database,
            "collection": request.collection
        }
    
    except PyMongoError as exc:
        log.error("find_documents_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.get("/documents/find_one", summary="Find one document")
async def find_one_document(
    database: str = Query(description="Database name"),
    collection: str = Query(description="Collection name"),
    filter_json: str = Query(default="{}", description="Filter as JSON string")
) -> dict[str, Any]:
    """Find a single document."""
    try:
        import json
        filter_dict = json.loads(filter_json)
        
        client = _get_mongo_client()
        db = client[database]
        coll = db[collection]
        
        document = await coll.find_one(filter_dict)
        
        client.close()
        
        if document:
            document["_id"] = str(document["_id"])
            return {"found": True, "document": document}
        else:
            return {"found": False, "document": None}
    
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in filter")
    except PyMongoError as exc:
        log.error("find_one_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.put("/documents/update_one", summary="Update one document")
async def update_one_document(request: UpdateDocumentRequest) -> dict[str, Any]:
    """Update a single document."""
    try:
        client = _get_mongo_client()
        db = client[request.database]
        collection = db[request.collection]
        
        result = await collection.update_one(
            filter=request.filter,
            update=request.update,
            upsert=request.upsert
        )
        
        client.close()
        
        log.info("update_one_document", 
                database=request.database, 
                collection=request.collection,
                matched=result.matched_count,
                modified=result.modified_count,
                upserted=result.upserted_id is not None)
        
        return {
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            "database": request.database,
            "collection": request.collection
        }
    
    except PyMongoError as exc:
        log.error("update_one_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.put("/documents/update_many", summary="Update multiple documents")
async def update_many_documents(request: UpdateDocumentRequest) -> dict[str, Any]:
    """Update multiple documents matching the filter."""
    try:
        client = _get_mongo_client()
        db = client[request.database]
        collection = db[request.collection]
        
        result = await collection.update_many(
            filter=request.filter,
            update=request.update,
            upsert=request.upsert
        )
        
        client.close()
        
        log.info("update_many_documents", 
                database=request.database, 
                collection=request.collection,
                matched=result.matched_count,
                modified=result.modified_count)
        
        return {
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            "database": request.database,
            "collection": request.collection
        }
    
    except PyMongoError as exc:
        log.error("update_many_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.delete("/documents/delete_one", summary="Delete one document")
async def delete_one_document(request: DeleteDocumentRequest) -> dict[str, Any]:
    """Delete a single document matching the filter."""
    try:
        client = _get_mongo_client()
        db = client[request.database]
        collection = db[request.collection]
        
        result = await collection.delete_one(request.filter)
        
        client.close()
        
        log.info("delete_one_document", 
                database=request.database, 
                collection=request.collection,
                deleted=result.deleted_count)
        
        return {
            "deleted_count": result.deleted_count,
            "database": request.database,
            "collection": request.collection
        }
    
    except PyMongoError as exc:
        log.error("delete_one_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.delete("/documents/delete_many", summary="Delete multiple documents")
async def delete_many_documents(request: DeleteDocumentRequest) -> dict[str, Any]:
    """Delete all documents matching the filter."""
    try:
        client = _get_mongo_client()
        db = client[request.database]
        collection = db[request.collection]
        
        result = await collection.delete_many(request.filter)
        
        client.close()
        
        log.warning("delete_many_documents", 
                   database=request.database, 
                   collection=request.collection,
                   deleted=result.deleted_count)
        
        return {
            "deleted_count": result.deleted_count,
            "database": request.database,
            "collection": request.collection
        }
    
    except PyMongoError as exc:
        log.error("delete_many_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.post("/aggregation", summary="Run aggregation pipeline")
async def run_aggregation(request: AggregationRequest) -> dict[str, Any]:
    """Execute an aggregation pipeline."""
    try:
        client = _get_mongo_client()
        db = client[request.database]
        collection = db[request.collection]
        
        cursor = collection.aggregate(request.pipeline)
        results = await cursor.to_list(length=1000)
        
        # Convert ObjectId to string
        for doc in results:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
        
        client.close()
        
        log.info("run_aggregation", 
                database=request.database, 
                collection=request.collection,
                stages=len(request.pipeline),
                results=len(results))
        
        return {
            "results": results,
            "count": len(results),
            "pipeline_stages": len(request.pipeline),
            "database": request.database,
            "collection": request.collection
        }
    
    except PyMongoError as exc:
        log.error("run_aggregation_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.post("/indexes/create", summary="Create an index")
async def create_index(request: CreateIndexRequest) -> dict[str, Any]:
    """Create an index on a collection."""
    try:
        client = _get_mongo_client()
        db = client[request.database]
        collection = db[request.collection]
        
        index_spec = [(key, direction) for key, direction in request.keys.items()]
        
        index_name = await collection.create_index(
            index_spec,
            unique=request.unique,
            name=request.name
        )
        
        client.close()
        
        log.info("create_index", 
                database=request.database, 
                collection=request.collection,
                index_name=index_name)
        
        return {
            "created": True,
            "index_name": index_name,
            "database": request.database,
            "collection": request.collection
        }
    
    except PyMongoError as exc:
        log.error("create_index_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.get("/indexes/list", summary="List indexes")
async def list_indexes(
    database: str = Query(description="Database name"),
    collection: str = Query(description="Collection name")
) -> dict[str, Any]:
    """List all indexes on a collection."""
    try:
        client = _get_mongo_client()
        db = client[database]
        coll = db[collection]
        
        indexes = await coll.list_indexes().to_list(length=100)
        
        client.close()
        
        return {
            "indexes": indexes,
            "count": len(indexes),
            "database": database,
            "collection": collection
        }
    
    except PyMongoError as exc:
        log.error("list_indexes_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")


@router.get("/stats", summary="Get collection statistics")
async def get_collection_stats(
    database: str = Query(description="Database name"),
    collection: str = Query(description="Collection name")
) -> dict[str, Any]:
    """Get statistics for a collection."""
    try:
        client = _get_mongo_client()
        db = client[database]
        
        stats = await db.command("collStats", collection)
        
        client.close()
        
        return {
            "database": database,
            "collection": collection,
            "stats": {
                "count": stats.get("count", 0),
                "size": stats.get("size", 0),
                "storage_size": stats.get("storageSize", 0),
                "indexes": stats.get("nindexes", 0),
                "avg_obj_size": stats.get("avgObjSize", 0)
            }
        }
    
    except PyMongoError as exc:
        log.error("get_stats_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"MongoDB error: {exc}")
