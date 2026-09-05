"""Short-term memory: Postgres.

Everything about a conversation lands in Postgres - the turns, the agent steps,
the tool calls, the token counts, the breaker state at call time. The prompt
window is a *view* over that, not the storage itself, which is why we can widen
the window or replay a run without having lost anything.

When a thread outgrows the window we roll the oldest turns into a summary and
keep the tail verbatim. The summary is stored on the conversation row so it
survives a restart.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logging import get_logger
from app.db.repositories import ConversationRepository, MessageRepository

log = get_logger(__name__)

SUMMARY_PROMPT = (
    "Condense the conversation below into a factual brief for an assistant that will continue it.\n"
    "Keep: decisions made, constraints the user stated, names and identifiers, open questions.\n"
    "Drop: pleasantries, restatements, anything the assistant said that the user did not act on.\n"
    "Write plain prose under 250 words. Do not editorialise.\n\n"
    "Existing brief (may be empty):\n{existing}\n\nNew turns:\n{turns}"
)


class ShortTermMemory:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.messages = MessageRepository(session)
        self.conversations = ConversationRepository(session)

    async def window(self, conversation_id: uuid.UUID, limit: int | None = None) -> list[dict[str, str]]:
        """The recent turns replayed into the prompt, oldest first."""
        limit = limit or settings.agent.short_term_window
        rows = await self.messages.history(conversation_id, limit=limit, roles=["user", "assistant"])
        return [{"role": m.role, "content": m.content} for m in rows if m.content]

    async def record_turn(
        self,
        conversation_id: uuid.UUID,
        *,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        **fields: Any,
    ) -> Any:
        return await self.messages.add(conversation_id, role, content, meta=metadata or {}, **fields)

    async def maybe_summarise(self, conversation_id: uuid.UUID, llm: Any) -> str | None:
        """Roll older turns into the running summary once the thread gets long.

        Called after a turn completes, never on the request path.
        """
        conv = await self.conversations.get(conversation_id)
        window = settings.agent.short_term_window
        pending = await self.messages.since_seq(conversation_id, conv.summarised_through_seq)
        if len(pending) <= window * 2:
            return conv.summary

        to_fold = pending[: len(pending) - window]
        turns = "\n".join(f"{m.role}: {m.content[:1500]}" for m in to_fold if m.content)
        if not turns.strip():
            return conv.summary

        try:
            response = await llm.ainvoke(
                SUMMARY_PROMPT.format(existing=conv.summary or "(none)", turns=turns)
            )
            summary = getattr(response, "content", str(response))
            if isinstance(summary, list):
                summary = "".join(p.get("text", "") for p in summary if isinstance(p, dict))
        except Exception as exc:
            log.warning("summarisation_failed", error=str(exc)[:300])
            return conv.summary

        conv.summary = summary.strip()
        conv.summarised_through_seq = to_fold[-1].seq
        await self.session.flush()
        log.info(
            "conversation_summarised",
            conversation_id=str(conversation_id),
            through_seq=conv.summarised_through_seq,
        )
        return conv.summary
