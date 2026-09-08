"""Repository layer.

Routes and agents never issue raw SQL. Everything funnels through these classes
so audit writes, sequence allocation and JSONB shape stay in one place.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import (
    AgentRun,
    AgentStep,
    AuditLog,
    Conversation,
    Document,
    IngestionJob,
    Message,
    UserSetting,
)


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> Conversation:
        conv = Conversation(**kwargs)
        self.session.add(conv)
        await self.session.flush()
        return conv

    async def get(self, conversation_id: uuid.UUID, user_id: str | None = None) -> Conversation:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        if user_id:
            stmt = stmt.where(Conversation.user_id == user_id)
        conv = (await self.session.execute(stmt)).scalar_one_or_none()
        if conv is None:
            raise NotFoundError(f"Conversation {conversation_id} not found")
        return conv

    async def list_for_user(
        self, user_id: str, *, limit: int = 50, offset: int = 0, include_archived: bool = False
    ) -> tuple[Sequence[Conversation], int]:
        stmt = select(Conversation).where(Conversation.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(Conversation.is_archived.is_(False))
        total = (
            await self.session.execute(
                select(func.count()).select_from(stmt.subquery())
            )
        ).scalar_one()
        stmt = stmt.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(stmt)).scalars().all()
        return rows, total

    async def update(self, conversation_id: uuid.UUID, **fields: Any) -> Conversation:
        conv = await self.get(conversation_id)
        for key, value in fields.items():
            if value is not None and hasattr(conv, key):
                setattr(conv, key, value)
        await self.session.flush()
        return conv

    async def delete(self, conversation_id: uuid.UUID, user_id: str | None = None) -> None:
        conv = await self.get(conversation_id, user_id)
        await self.session.delete(conv)

    async def add_usage(self, conversation_id: uuid.UUID, tokens: int, cost_usd: float) -> None:
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(
                total_tokens=Conversation.total_tokens + tokens,
                total_cost_usd=Conversation.total_cost_usd + cost_usd,
            )
        )


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def next_seq(self, conversation_id: uuid.UUID) -> int:
        current = (
            await self.session.execute(
                select(func.coalesce(func.max(Message.seq), 0)).where(Message.conversation_id == conversation_id)
            )
        ).scalar_one()
        return int(current) + 1

    async def add(self, conversation_id: uuid.UUID, role: str, content: str, **kwargs: Any) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            seq=await self.next_seq(conversation_id),
            role=role,
            content=content,
            **kwargs,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def history(
        self, conversation_id: uuid.UUID, *, limit: int | None = None, roles: Sequence[str] | None = None
    ) -> list[Message]:
        stmt = select(Message).where(Message.conversation_id == conversation_id)
        if roles:
            stmt = stmt.where(Message.role.in_(roles))
        stmt = stmt.order_by(Message.seq.desc())
        if limit:
            stmt = stmt.limit(limit)
        rows = list((await self.session.execute(stmt)).scalars().all())
        rows.reverse()
        return rows

    async def since_seq(self, conversation_id: uuid.UUID, seq: int) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.seq > seq)
            .order_by(Message.seq)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def update_message(self, message_id: uuid.UUID, **fields: Any) -> None:
        await self.session.execute(update(Message).where(Message.id == message_id).values(**fields))

    async def delete_from_seq(self, conversation_id: uuid.UUID, seq: int) -> None:
        """Used when a user edits a turn - drop everything after it."""
        await self.session.execute(
            delete(Message).where(Message.conversation_id == conversation_id, Message.seq >= seq)
        )


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start(self, **kwargs: Any) -> AgentRun:
        run = AgentRun(status="running", started_at=datetime.now(UTC), **kwargs)
        self.session.add(run)
        await self.session.flush()
        return run

    async def finish(self, run_id: uuid.UUID, *, status: str, error: str | None = None, tokens: int = 0) -> None:
        run = (await self.session.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one_or_none()
        if run is None:
            return
        run.status = status
        run.error = error
        run.total_tokens = tokens
        run.finished_at = datetime.now(UTC)
        if run.started_at:
            started = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=UTC)
            run.duration_ms = int((run.finished_at - started).total_seconds() * 1000)
        await self.session.flush()

    async def add_step(self, run_id: uuid.UUID, **kwargs: Any) -> AgentStep:
        index = (
            await self.session.execute(
                select(func.coalesce(func.max(AgentStep.step_index), -1)).where(AgentStep.run_id == run_id)
            )
        ).scalar_one()
        step = AgentStep(run_id=run_id, step_index=int(index) + 1, **kwargs)
        self.session.add(step)
        await self.session.flush()
        return step

    async def get_with_steps(self, run_id: uuid.UUID) -> AgentRun:
        run = (await self.session.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one_or_none()
        if run is None:
            raise NotFoundError(f"Run {run_id} not found")
        await self.session.refresh(run, ["steps"])
        return run

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> Sequence[AgentRun]:
        stmt = (
            select(AgentRun)
            .where(AgentRun.conversation_id == conversation_id)
            .order_by(AgentRun.created_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> Document:
        doc = Document(**kwargs)
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get(self, document_id: uuid.UUID) -> Document:
        doc = (await self.session.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
        if doc is None:
            raise NotFoundError(f"Document {document_id} not found")
        return doc

    async def by_checksum(self, user_id: str, checksum: str) -> Document | None:
        stmt = select(Document).where(Document.user_id == user_id, Document.checksum_sha256 == checksum)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(
        self, user_id: str, *, limit: int = 100, offset: int = 0
    ) -> tuple[Sequence[Document], int]:
        stmt = select(Document).where(Document.user_id == user_id)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        return (await self.session.execute(stmt)).scalars().all(), total

    async def set_status(self, document_id: uuid.UUID, status: str, **fields: Any) -> None:
        await self.session.execute(
            update(Document).where(Document.id == document_id).values(status=status, **fields)
        )

    async def delete(self, document_id: uuid.UUID) -> Document:
        doc = await self.get(document_id)
        await self.session.delete(doc)
        return doc

    async def add_job(self, **kwargs: Any) -> IngestionJob:
        job = IngestionJob(**kwargs)
        self.session.add(job)
        await self.session.flush()
        return job


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: str) -> UserSetting | None:
        stmt = select(UserSetting).where(UserSetting.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(self, user_id: str, **fields: Any) -> UserSetting:
        existing = await self.get(user_id)
        if existing is None:
            existing = UserSetting(user_id=user_id, **fields)
            self.session.add(existing)
        else:
            for key, value in fields.items():
                if value is not None and hasattr(existing, key):
                    setattr(existing, key, value)
        await self.session.flush()
        return existing


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        user_id: str | None = None,
        request_id: str | None = None,
        outcome: str = "success",
        ip_address: str | None = None,
        user_agent: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            created_at=datetime.now(UTC),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            request_id=request_id,
            outcome=outcome,
            ip_address=ip_address,
            user_agent=user_agent,
            detail=detail or {},
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def search(
        self,
        *,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        outcome: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Sequence[AuditLog], int]:
        stmt = select(AuditLog)
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        if outcome:
            stmt = stmt.where(AuditLog.outcome == outcome)
        if since:
            stmt = stmt.where(AuditLog.created_at >= since)
        if until:
            stmt = stmt.where(AuditLog.created_at <= until)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        return (await self.session.execute(stmt)).scalars().all(), total
