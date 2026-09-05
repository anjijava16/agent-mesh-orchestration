"""The contract every framework adapter implements.

This is the most important file in the repo. Four very different runtimes
(ADK, LangGraph, DeepAgents, Claude Agent SDK) each have their own event model.
We normalise all of them into one `AgentEvent` stream so the API layer, the
persistence layer and the React client never learn which framework ran.

If you add a fifth framework, you implement `AgentRuntime` and register it.
Nothing else changes.
"""
from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config import AgentFramework, ModelProvider


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    PLAN = "plan"                 # orchestrator published a plan
    AGENT_STARTED = "agent_started"
    AGENT_FINISHED = "agent_finished"
    TOKEN = "token"               # streamed assistant text
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    CITATION = "citation"
    HANDOFF = "handoff"
    USAGE = "usage"
    ERROR = "error"
    RUN_FINISHED = "run_finished"
    HEARTBEAT = "heartbeat"


@dataclass
class AgentEvent:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    agent: str | None = None
    run_id: str | None = None
    ts: float = field(default_factory=time.time)

    def to_sse(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "agent": self.agent,
            "run_id": self.run_id,
            "ts": self.ts,
            "data": self.data,
        }


@dataclass
class RunContext:
    """Everything a runtime needs to execute one turn."""

    conversation_id: uuid.UUID
    run_id: uuid.UUID
    user_id: str
    message: str
    history: list[dict[str, str]] = field(default_factory=list)
    long_term_memories: list[dict[str, Any]] = field(default_factory=list)
    summary: str | None = None
    document_ids: list[str] = field(default_factory=list)
    provider: ModelProvider = ModelProvider.ANTHROPIC
    model: str = "claude-sonnet-4-6"
    temperature: float = 0.2
    max_tokens: int = 4096
    enabled_agents: list[str] = field(default_factory=list)
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def memory_block(self) -> str:
        """Rendered into the system prompt by every adapter, identically."""
        parts: list[str] = []
        if self.summary:
            parts.append(f"Conversation summary so far:\n{self.summary}")
        if self.long_term_memories:
            lines = "\n".join(
                f"- ({m.get('kind', 'fact')}) {m.get('content', '')}" for m in self.long_term_memories
            )
            parts.append(f"Relevant long-term memory about this user:\n{lines}")
        return "\n\n".join(parts)


@dataclass
class RunResult:
    text: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentRuntime(ABC):
    """Every framework adapter subclasses this."""

    framework: AgentFramework
    display_name: str = ""
    description: str = ""

    @abstractmethod
    async def stream(self, ctx: RunContext) -> AsyncIterator[AgentEvent]:
        """Yield normalised events. Must always terminate with RUN_FINISHED or ERROR."""
        raise NotImplementedError

    async def run(self, ctx: RunContext) -> RunResult:
        """Non-streaming convenience path, assembled from the event stream."""
        chunks: list[str] = []
        citations: list[dict[str, Any]] = []
        steps: list[dict[str, Any]] = []
        usage: dict[str, int] = {}
        error: str | None = None

        async for event in self.stream(ctx):
            if event.type is EventType.TOKEN:
                chunks.append(event.data.get("text", ""))
            elif event.type is EventType.CITATION:
                citations.extend(event.data.get("citations", []))
            elif event.type in (EventType.TOOL_CALL, EventType.TOOL_RESULT, EventType.AGENT_FINISHED):
                steps.append({"type": event.type.value, "agent": event.agent, **event.data})
            elif event.type is EventType.USAGE:
                for key, value in event.data.items():
                    if isinstance(value, int):
                        usage[key] = usage.get(key, 0) + value
            elif event.type is EventType.ERROR:
                error = event.data.get("message")
            elif event.type is EventType.RUN_FINISHED:
                if event.data.get("text") and not chunks:
                    chunks.append(event.data["text"])

        return RunResult(text="".join(chunks), citations=citations, steps=steps, usage=usage, error=error)

    async def health(self) -> dict[str, Any]:
        return {"framework": self.framework.value, "available": True}
