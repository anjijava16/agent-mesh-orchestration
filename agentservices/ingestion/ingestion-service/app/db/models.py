"""Postgres schema.

Short-term memory lives here in full: every conversation, every message, every
agent step, every tool call, with the JSONB metadata blob that lets us replay a
run exactly as it happened. Long-term memory is a *derivative* of this, written
to OpenSearch by the memory manager.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Conversation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "conversations"

    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="New conversation")
    framework: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Per-conversation overrides: temperature, enabled agents, tool allowlist...
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Rolling summary that keeps long threads inside the context window.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarised_through_seq: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.seq"
    )

    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user|assistant|system|tool
    content: Mapped[str] = mapped_column(Text, default="")
    agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    framework: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    finish_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Everything else we want to keep for replay: tool calls, citations,
    # routing decisions, breaker state at call time, request id, trace id.
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_message_conversation_seq"),
        CheckConstraint("role in ('user','assistant','system','tool')", name="role_enum"),
        Index("ix_messages_conv_seq", "conversation_id", "seq"),
        Index("ix_messages_metadata_gin", "metadata", postgresql_using="gin"),
    )


class AgentRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One orchestrator invocation - the parent span of a whole multi-agent turn."""

    __tablename__ = "agent_runs"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    framework: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    steps: Mapped[list[AgentStep]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentStep.step_index"
    )


class AgentStep(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One sub-agent or tool execution inside a run."""

    __tablename__ = "agent_steps"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(128), index=True)
    step_type: Mapped[str] = mapped_column(String(32))  # agent|tool|route|reflect
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[AgentRun] = relationship(back_populates="steps")


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An uploaded file and the state of its ingestion pipeline."""

    __tablename__ = "documents"

    user_id: Mapped[str] = mapped_column(String(128), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_backend: Mapped[str] = mapped_column(String(16), default="minio")
    storage_key: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    # uploaded -> queued -> parsing -> chunking -> embedding -> indexed | failed
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("user_id", "checksum_sha256", name="uq_document_user_checksum"),
    )


class IngestionJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_jobs"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(String(128), index=True)
    stage: Mapped[str] = mapped_column(String(32), default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class UserSetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-user UI/runtime preferences: framework, model, temperature, toggles."""

    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    framework: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    enabled_agents: Mapped[list[str]] = mapped_column(JSONB, default=list)
    use_long_term_memory: Mapped[bool] = mapped_column(Boolean, default=True)
    use_hybrid_search: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Append-only. Never updated, never deleted by the application."""

    __tablename__ = "audit_logs"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(String(32), default="success", index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    __table_args__ = (Index("ix_audit_action_created", "action", "created_at"),)
