"""MCP Documents Server.

Exposes document management operations as MCP tools.
Run: python -m app.server
"""
from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from app.config import settings
from app.logging_config import configure_logging, get_logger

configure_logging(settings.log_level)
log = get_logger(__name__)

mcp = FastMCP(
    name=settings.mcp_server_name,
    instructions=(
        "Document management system. Use list_documents to see available documents, "
        "get_document_info for metadata, and search_documents for content queries. "
        "Always pass the user_id from the authenticated principal."
    ),
)


@mcp.tool
def list_documents(
    user_id: Annotated[str, Field(description="Verified user identifier")],
    limit: Annotated[int, Field(description="Max documents to return")] = 20,
    offset: Annotated[int, Field(description="Pagination offset")] = 0,
) -> dict[str, Any]:
    """List all documents uploaded by the user.
    
    Returns document metadata including filename, status, chunk count, and upload time.
    Use this before get_document_info when the user hasn't named a specific document.
    """
    log.info("list_documents", user_id=user_id, limit=limit, offset=offset)
    
    # TODO: Implement database query
    # from app.db import get_documents
    # documents = await get_documents(user_id=user_id, limit=limit, offset=offset)
    
    return {
        "user_id": user_id,
        "count": 0,
        "documents": [],
        "limit": limit,
        "offset": offset,
        "note": "Placeholder - implement database query in app/db.py",
    }


@mcp.tool
def get_document_info(
    user_id: Annotated[str, Field(description="Verified user identifier")],
    document_id: Annotated[str, Field(description="Document UUID")],
) -> dict[str, Any]:
    """Get detailed metadata for a specific document.
    
    Returns full document metadata including ingestion status, chunk count,
    page count, content type, checksum, and error details if failed.
    """
    log.info("get_document_info", user_id=user_id, document_id=document_id)
    
    # TODO: Implement database query
    # from app.db import get_document_by_id
    # document = await get_document_by_id(document_id=document_id, user_id=user_id)
    
    return {
        "user_id": user_id,
        "document_id": document_id,
        "status": "indexed",
        "note": "Placeholder - implement database query in app/db.py",
    }


@mcp.tool
def search_documents(
    user_id: Annotated[str, Field(description="Verified user identifier")],
    query: Annotated[str, Field(description="Search query")],
    document_ids: Annotated[list[str] | None, Field(description="Limit search to specific documents")] = None,
    top_k: Annotated[int, Field(description="Number of results")] = 5,
) -> dict[str, Any]:
    """Search across user's documents with hybrid retrieval (BM25 + vector).
    
    Returns the most relevant passages with document context, page numbers,
    and relevance scores. Results include citations for transparency.
    """
    log.info("search_documents", user_id=user_id, query=query, document_ids=document_ids, top_k=top_k)
    
    # TODO: Implement vector search
    # from app.search import hybrid_search
    # results = await hybrid_search(query=query, user_id=user_id, document_ids=document_ids, top_k=top_k)
    
    return {
        "user_id": user_id,
        "query": query,
        "results": [],
        "note": "Placeholder - implement hybrid search in app/search.py",
    }


@mcp.tool
def get_document_stats(
    user_id: Annotated[str, Field(description="Verified user identifier")],
) -> dict[str, Any]:
    """Get summary statistics about the user's document corpus.
    
    Returns total document count, total chunks, storage used, and breakdown by status.
    """
    log.info("get_document_stats", user_id=user_id)
    
    # TODO: Implement stats aggregation
    # from app.db import get_user_document_stats
    # stats = await get_user_document_stats(user_id=user_id)
    
    return {
        "user_id": user_id,
        "total_documents": 0,
        "total_chunks": 0,
        "storage_bytes": 0,
        "by_status": {},
        "note": "Placeholder - implement stats in app/db.py",
    }


if __name__ == "__main__":
    log.info(
        "mcp_documents_server_starting",
        name=settings.mcp_server_name,
        port=settings.mcp_server_port,
        host=settings.mcp_server_host,
    )
    mcp.run(
        transport="sse",
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
    )
