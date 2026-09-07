"""MCP Search Server.

Exposes web search and corpus overview operations.
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
        "Web search and external knowledge retrieval. Use web_search for current "
        "information not in the document corpus. Use get_corpus_overview to understand "
        "what documents are available before searching."
    ),
)


@mcp.tool
def web_search(
    query: Annotated[str, Field(description="Search query")],
    max_results: Annotated[int, Field(description="Max results to return")] = 5,
) -> dict[str, Any]:
    """Search the web using Tavily or DuckDuckGo.
    
    Returns recent, relevant web results with titles, URLs, and snippets.
    Use this when the user asks for current information not in their documents.
    """
    log.info("web_search", query=query, max_results=max_results)
    
    # TODO: Implement web search
    # from app.web_search import search_web
    # results = await search_web(query=query, max_results=max_results, provider=settings.search_provider)
    
    return {
        "query": query,
        "provider": settings.search_provider,
        "results": [],
        "note": "Placeholder - implement web_search in app/web_search.py",
    }


@mcp.tool
def get_corpus_overview(
    user_id: Annotated[str, Field(description="Verified user identifier")],
) -> dict[str, Any]:
    """Get summary statistics about the user's document corpus.
    
    Returns document count, chunk count, content type breakdown, and recent uploads.
    Call this before search_documents to understand what's available.
    """
    log.info("get_corpus_overview", user_id=user_id)
    
    # TODO: Implement corpus stats
    # from app.corpus import get_user_corpus_stats
    # stats = await get_user_corpus_stats(user_id=user_id)
    
    return {
        "user_id": user_id,
        "total_documents": 0,
        "total_chunks": 0,
        "by_content_type": {},
        "recent_uploads": [],
        "note": "Placeholder - implement get_corpus_overview in app/corpus.py",
    }


if __name__ == "__main__":
    log.info(
        "mcp_search_server_starting",
        name=settings.mcp_server_name,
        port=settings.mcp_server_port,
        host=settings.mcp_server_host,
    )
    mcp.run(
        transport="sse",
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
    )
