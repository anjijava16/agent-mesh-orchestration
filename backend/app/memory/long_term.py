"""Long-term memory: OpenSearch.

Postgres holds the transcript. This holds the *distillate* - durable facts,
stated preferences, decisions - embedded so we can recall them semantically in a
later conversation that shares no keywords with the one that produced them.

Two design choices worth stating:
  * Extraction is a separate LLM pass that runs after the turn, off the request
    path. A user should never wait on memory writing.
  * Recall is scoped by user_id at the query level, inside the kNN filter, so a
    tenant boundary is a query constraint rather than a post-filter.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.core.logging import get_logger
from app.core.resilience import OPENSEARCH_BREAKER, with_resilience
from app.llm.registry import get_embedder
from app.search.client import get_opensearch
from app.search.hybrid import hybrid_search

log = get_logger(__name__)

EXTRACTION_PROMPT = (
    "Read the exchange below and extract durable facts worth remembering in a future, unrelated "
    "conversation with this user.\n\n"
    "Extract only: stated preferences, stable facts about their work or context, decisions they made, "
    "and constraints they set. One item per fact.\n"
    "Do not extract: transient task state, anything you inferred rather than they stated, "
    "pleasantries, or anything about a topic that closes with this turn.\n"
    "Return JSON only: {{\"memories\": [{{\"kind\": \"fact|preference|decision\", \"content\": \"...\", "
    "\"importance\": 0.0-1.0}}]}}\n"
    "Return an empty list when nothing qualifies. Most turns qualify for nothing.\n\n"
    "User: {user_message}\nAssistant: {assistant_message}"
)


class LongTermMemory:
    def __init__(self) -> None:
        self.index = settings.opensearch.memory_index
        self.embedder = get_embedder()

    @with_resilience(breaker=OPENSEARCH_BREAKER, timeout=20, label="ltm.write")
    async def _index_doc(self, doc_id: str, body: dict[str, Any]) -> None:
        await get_opensearch().index(index=self.index, id=doc_id, body=body, refresh=False)

    async def write(
        self,
        *,
        user_id: str,
        conversation_id: uuid.UUID,
        content: str,
        kind: str = "fact",
        importance: float = 0.5,
        framework: str | None = None,
        source_message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        content = content.strip()
        if not content:
            return None
        try:
            vector = await self.embedder.embed_query(content)
        except Exception as exc:
            log.warning("ltm_embed_failed", error=str(exc)[:200])
            return None

        memory_id = str(uuid.uuid4())
        await self._index_doc(
            memory_id,
            {
                "memory_id": memory_id,
                "user_id": user_id,
                "conversation_id": str(conversation_id),
                "kind": kind,
                "content": content,
                "embedding": vector,
                "importance": max(0.0, min(importance, 1.0)),
                "framework": framework,
                "source_message_id": source_message_id,
                "created_at": datetime.now(UTC).isoformat(),
                "last_accessed_at": datetime.now(UTC).isoformat(),
                "access_count": 0,
                "metadata": metadata or {},
            },
        )
        return memory_id

    async def recall(self, query: str, *, user_id: str, top_k: int | None = None) -> list[dict[str, Any]]:
        top_k = top_k or settings.agent.long_term_top_k
        try:
            hits = await hybrid_search(
                query, embedder=self.embedder, user_id=user_id, top_k=top_k, index=self.index
            )
        except Exception as exc:
            log.warning("ltm_recall_failed", error=str(exc)[:300])
            return []
        return [
            {"content": h.content, "kind": h.metadata.get("kind", "fact"), "score": round(h.score, 4)}
            for h in hits
            if h.content
        ]

    async def extract_and_store(
        self,
        *,
        llm: Any,
        user_id: str,
        conversation_id: uuid.UUID,
        user_message: str,
        assistant_message: str,
        framework: str | None = None,
    ) -> int:
        """Post-turn distillation. Best-effort by design."""
        if not settings.agent.enable_long_term_memory:
            return 0
        try:
            response = await llm.ainvoke(
                EXTRACTION_PROMPT.format(
                    user_message=user_message[:4000], assistant_message=assistant_message[:4000]
                )
            )
            raw = getattr(response, "content", str(response))
            if isinstance(raw, list):
                raw = "".join(p.get("text", "") for p in raw if isinstance(p, dict))
            payload = json.loads(_strip_fences(raw))
        except Exception as exc:
            log.warning("ltm_extraction_failed", error=str(exc)[:300])
            return 0

        written = 0
        for item in payload.get("memories", [])[:10]:
            if not isinstance(item, dict) or not item.get("content"):
                continue
            ok = await self.write(
                user_id=user_id,
                conversation_id=conversation_id,
                content=str(item["content"]),
                kind=str(item.get("kind", "fact")),
                importance=float(item.get("importance", 0.5) or 0.5),
                framework=framework,
            )
            written += 1 if ok else 0
        if written:
            log.info("ltm_written", count=written, user_id=user_id)
        return written

    async def forget(self, *, user_id: str, memory_id: str | None = None,
                     conversation_id: uuid.UUID | None = None) -> int:
        """Right-to-be-forgotten support. Deletes by id or by whole conversation."""
        client = get_opensearch()
        must: list[dict[str, Any]] = [{"term": {"user_id": user_id}}]
        if memory_id:
            must.append({"term": {"memory_id": memory_id}})
        if conversation_id:
            must.append({"term": {"conversation_id": str(conversation_id)}})
        res = await client.delete_by_query(
            index=self.index, body={"query": {"bool": {"filter": must}}}, refresh=True
        )
        return int(res.get("deleted", 0))


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


_ltm: LongTermMemory | None = None


def get_long_term_memory() -> LongTermMemory:
    global _ltm
    if _ltm is None:
        _ltm = LongTermMemory()
    return _ltm
