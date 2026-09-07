"""MCP Memory Server.

Exposes long-term memory operations as MCP tools.
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
        "Long-term memory system. Use recall_memories to find relevant facts from "
        "past conversations, store_memory to save new durable facts, and forget_memory "
        "for GDPR compliance. Always include the user_id from the authenticated principal."
    ),
)


@mcp.tool
def recall_memories(
    user_id: Annotated[str, Field(description="Verified user identifier")],
    query: Annotated[str, Field(description="Query to find relevant memories")],
    conversation_id: Annotated[str | None, Field(description="Limit to specific conversation")] = None,
    top_k: Annotated[int, Field(description="Number of memories to return")] = 5,
) -> dict[str, Any]:
    """Recall semantically relevant long-term memories.
    
    Returns facts, preferences, decisions, and constraints extracted from past
    conversations. Each memory includes the source conversation, importance score,
    and creation time.
    """
    log.info("recall_memories", user_id=user_id, query=query, conversation_id=conversation_id, top_k=top_k)
    
    # TODO: Implement memory recall
    # from app.memory import hybrid_recall
    # memories = await hybrid_recall(user_id=user_id, query=query, conversation_id=conversation_id, top_k=top_k)
    
    return {
        "user_id": user_id,
        "query": query,
        "memories": [],
        "note": "Placeholder - implement recall in app/memory.py",
    }


@mcp.tool
def store_memory(
    user_id: Annotated[str, Field(description="Verified user identifier")],
    content: Annotated[str, Field(description="Memory content to store")],
    conversation_id: Annotated[str | None, Field(description="Source conversation ID")] = None,
    importance: Annotated[int, Field(description="Importance score 1-10")] = 5,
    kind: Annotated[str, Field(description="Memory type")] = "fact",
) -> dict[str, Any]:
    """Store a new long-term memory fact.
    
    Extracts durable information (preferences, decisions, constraints) and indexes
    it with embeddings for future semantic recall. Not every turn should produce a memory.
    """
    log.info("store_memory", user_id=user_id, content_len=len(content), importance=importance, kind=kind)
    
    # TODO: Implement memory storage
    # from app.memory import store_memory_fact
    # memory_id = await store_memory_fact(user_id=user_id, content=content, conversation_id=conversation_id, importance=importance, kind=kind)
    
    return {
        "user_id": user_id,
        "memory_id": "placeholder-uuid",
        "status": "stored",
        "note": "Placeholder - implement store in app/memory.py",
    }


@mcp.tool
def forget_memory(
    user_id: Annotated[str, Field(description="Verified user identifier")],
    memory_id: Annotated[str | None, Field(description="Memory UUID to delete")] = None,
    conversation_id: Annotated[str | None, Field(description="Delete all memories from a conversation")] = None,
) -> dict[str, Any]:
    """Delete specific memory or all memories from a conversation.
    
    GDPR right-to-be-forgotten support. Provide either memory_id (single deletion)
    or conversation_id (bulk deletion). This operation is irreversible.
    """
    log.info("forget_memory", user_id=user_id, memory_id=memory_id, conversation_id=conversation_id)
    
    if not memory_id and not conversation_id:
        return {"error": "must provide either memory_id or conversation_id"}
    
    # TODO: Implement memory deletion
    # from app.memory import delete_memories
    # deleted = await delete_memories(user_id=user_id, memory_id=memory_id, conversation_id=conversation_id)
    
    return {
        "user_id": user_id,
        "deleted_count": 0,
        "status": "deleted",
        "note": "Placeholder - implement forget in app/memory.py",
    }


@mcp.tool
def list_memories(
    user_id: Annotated[str, Field(description="Verified user identifier")],
    conversation_id: Annotated[str | None, Field(description="Filter by conversation")] = None,
    limit: Annotated[int, Field(description="Max memories to return")] = 20,
    offset: Annotated[int, Field(description="Pagination offset")] = 0,
) -> dict[str, Any]:
    """List all long-term memories for a user with pagination.
    
    Returns memories sorted by creation time (newest first). Useful for
    memory management and debugging.
    """
    log.info("list_memories", user_id=user_id, conversation_id=conversation_id, limit=limit, offset=offset)
    
    # TODO: Implement memory listing
    # from app.memory import list_user_memories
    # memories = await list_user_memories(user_id=user_id, conversation_id=conversation_id, limit=limit, offset=offset)
    
    return {
        "user_id": user_id,
        "memories": [],
        "total": 0,
        "note": "Placeholder - implement list in app/memory.py",
    }


if __name__ == "__main__":
    log.info(
        "mcp_memory_server_starting",
        name=settings.mcp_server_name,
        port=settings.mcp_server_port,
        host=settings.mcp_server_host,
        vector_backend=settings.vector_backend,
    )
    mcp.run(
        transport="sse",
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
    )
