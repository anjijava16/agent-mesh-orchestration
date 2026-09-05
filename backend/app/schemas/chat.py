from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.config import AgentFramework, ModelProvider


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=32_000)
    conversation_id: uuid.UUID | None = None
    framework: AgentFramework | None = None
    provider: ModelProvider | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=64, le=32_000)
    enabled_agents: list[str] | None = None
    document_ids: list[str] | None = None
    use_long_term_memory: bool | None = None

    def overrides(self) -> dict[str, Any]:
        return {
            "framework": self.framework.value if self.framework else None,
            "provider": self.provider.value if self.provider else None,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "enabled_agents": self.enabled_agents,
            "use_long_term_memory": self.use_long_term_memory,
        }


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seq: int
    role: str
    content: str
    agent_name: str | None = None
    framework: str | None = None
    model: str | None = None
    latency_ms: int = 0
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="meta")


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    framework: str
    provider: str
    model: str
    is_archived: bool
    summary: str | None = None
    total_tokens: int
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    is_archived: bool | None = None
    system_prompt: str | None = None


class AgentStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step_index: int
    agent_name: str
    step_type: str
    tool_name: str | None
    status: str
    duration_ms: int
    input: dict[str, Any]
    output: dict[str, Any]


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    framework: str
    status: str
    duration_ms: int
    total_tokens: int
    error: str | None
    created_at: datetime
    steps: list[AgentStepOut] = Field(default_factory=list)


class Page(BaseModel):
    total: int
    limit: int
    offset: int
