from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import AgentFramework, ModelProvider


class SettingsIn(BaseModel):
    framework: AgentFramework | None = None
    provider: ModelProvider | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=64, le=32_000)
    enabled_agents: list[str] | None = None
    use_long_term_memory: bool | None = None
    use_hybrid_search: bool | None = None
    extra: dict[str, Any] | None = None


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    framework: str
    provider: str
    model: str
    temperature: float
    max_tokens: int
    enabled_agents: list[str]
    use_long_term_memory: bool
    use_hybrid_search: bool
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("extra", mode="before")
    @classmethod
    def _coerce_extra(cls, v: Any) -> dict[str, Any]:
        return v if v is not None else {}


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    chunk_count: int
    page_count: int
    error: str | None
    created_at: datetime
    updated_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    user_id: str | None
    request_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    detail: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=50)
    document_ids: list[str] | None = None
    rerank: bool = False


class HealthOut(BaseModel):
    status: str
    version: str
    environment: str
    dependencies: dict[str, Any]
    breakers: dict[str, Any]
