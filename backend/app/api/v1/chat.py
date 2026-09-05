"""Chat endpoints.

The streaming endpoint is SSE rather than a websocket. SSE survives proxies and
load balancers without extra configuration, reconnects on its own, and the
traffic here is one-directional - the client sends a request and reads events.
A websocket would be added complexity with no gain.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.agents.base import EventType
from app.agents.definitions import roster
from app.agents.registry import available_frameworks
from app.agents.service import ChatService
from app.api.deps import CurrentUser, DbSession, RequestId
from app.core.logging import conversation_id_ctx, get_logger
from app.db.repositories import AgentRunRepository, ConversationRepository, MessageRepository
from app.schemas.chat import (
    AgentRunOut,
    ChatRequest,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)

router = APIRouter(tags=["chat"])
log = get_logger(__name__)

HEARTBEAT_SECONDS = 15


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    session: DbSession,
    user: CurrentUser,
    req_id: RequestId,
    request: Request,
) -> StreamingResponse:
    """Server-sent events: one JSON object per agent event."""
    if body.conversation_id:
        conversation_id_ctx.set(str(body.conversation_id))
    service = ChatService(session)

    async def generator() -> AsyncIterator[str]:
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=256)

        async def produce() -> None:
            try:
                async for event in service.stream_turn(
                    user_id=user,
                    conversation_id=body.conversation_id,
                    message=body.message,
                    overrides=body.overrides(),
                    document_ids=body.document_ids,
                    request_id=req_id,
                ):
                    await queue.put(_sse(event.to_sse()))
            except Exception as exc:
                log.exception("chat_stream_failed")
                await queue.put(_sse({"type": EventType.ERROR.value,
                                      "data": {"message": f"{type(exc).__name__}: {exc}"[:400]}}))
            finally:
                await queue.put(None)

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    # Keep intermediaries from closing an idle connection while a
                    # long tool call is in flight.
                    yield ": heartbeat\n\n"
                    continue
                if item is None:
                    break
                yield item
                if await request.is_disconnected():
                    log.info("client_disconnected", request_id=req_id)
                    break
        finally:
            producer.cancel()
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # nginx: do not buffer the stream
        },
    )


@router.post("/chat")
async def chat_once(body: ChatRequest, session: DbSession, user: CurrentUser, req_id: RequestId) -> dict:
    """Non-streaming variant for scripts and evaluation harnesses."""
    service = ChatService(session)
    chunks: list[str] = []
    citations: list[dict] = []
    meta: dict = {}
    error: str | None = None

    async for event in service.stream_turn(
        user_id=user,
        conversation_id=body.conversation_id,
        message=body.message,
        overrides=body.overrides(),
        document_ids=body.document_ids,
        request_id=req_id,
    ):
        if event.type is EventType.TOKEN:
            chunks.append(event.data.get("text", ""))
        elif event.type is EventType.CITATION:
            citations.extend(event.data.get("citations", []))
        elif event.type is EventType.ERROR:
            error = event.data.get("message")
        elif event.type is EventType.RUN_FINISHED:
            meta = event.data

    if error and not chunks:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error)
    return {"answer": "".join(chunks), "citations": citations, "meta": meta, "error": error}


@router.get("/frameworks")
async def list_frameworks() -> dict:
    return {"frameworks": available_frameworks(), "agents": roster()}


# ------------------------------------------------------------ conversations
@router.get("/conversations", response_model=dict)
async def list_conversations(
    session: DbSession,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_archived: bool = False,
) -> dict:
    rows, total = await ConversationRepository(session).list_for_user(
        user, limit=limit, offset=offset, include_archived=include_archived
    )
    return {
        "items": [ConversationOut.model_validate(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: uuid.UUID, session: DbSession, user: CurrentUser) -> ConversationDetail:
    conversation = await ConversationRepository(session).get(conversation_id, user)
    messages = await MessageRepository(session).history(conversation_id)
    # Build from ConversationOut first to avoid touching the lazy 'messages'
    # relationship on the ORM object (which would trigger a MissingGreenlet).
    base = ConversationOut.model_validate(conversation)
    return ConversationDetail(
        **base.model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: uuid.UUID, body: ConversationUpdate, session: DbSession, user: CurrentUser
) -> ConversationOut:
    repo = ConversationRepository(session)
    await repo.get(conversation_id, user)
    updated = await repo.update(conversation_id, **body.model_dump(exclude_unset=True))
    return ConversationOut.model_validate(updated)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: uuid.UUID, session: DbSession, user: CurrentUser) -> None:
    await ConversationRepository(session).delete(conversation_id, user)


@router.get("/conversations/{conversation_id}/runs", response_model=list[AgentRunOut])
async def list_runs(conversation_id: uuid.UUID, session: DbSession, user: CurrentUser) -> list[AgentRunOut]:
    await ConversationRepository(session).get(conversation_id, user)
    runs = await AgentRunRepository(session).list_for_conversation(conversation_id)
    return [AgentRunOut.model_validate(r) for r in runs]


@router.get("/runs/{run_id}", response_model=AgentRunOut)
async def get_run(run_id: uuid.UUID, session: DbSession, user: CurrentUser) -> AgentRunOut:
    run = await AgentRunRepository(session).get_with_steps(run_id)
    return AgentRunOut.model_validate(run)
