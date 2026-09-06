"""Chat orchestration service.

Sits between the HTTP layer and the framework runtimes and owns everything that
must happen regardless of which runtime ran:

  load settings -> assemble memory -> open a run row -> stream events
  -> persist every step -> persist the assistant turn -> schedule post-turn work

Post-turn work (summarisation, long-term extraction) is deliberately fired after
the stream closes, in its own session, so a slow memory write cannot hold the
socket open.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentEvent, EventType, RunContext
from app.agents.definitions import DEFAULT_AGENTS
from app.agents.registry import get_runtime
from app.config import ModelProvider, settings
from app.core.logging import get_logger
from app.db.repositories import AgentRunRepository, AuditRepository, ConversationRepository, SettingsRepository
from app.db.session import session_scope
from app.llm.registry import ModelSpec, build_chat_model
from app.memory.long_term import get_long_term_memory
from app.memory.short_term import ShortTermMemory

log = get_logger(__name__)

# Strong references to fire-and-forget post-turn work.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)
        self.runs = AgentRunRepository(session)
        self.settings_repo = SettingsRepository(session)
        self.audit = AuditRepository(session)
        self.stm = ShortTermMemory(session)
        self.ltm = get_long_term_memory()

    async def resolve_config(self, user_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
        """Precedence: request body > stored user setting > config.py default."""
        stored = await self.settings_repo.get(user_id)
        base = {
            "framework": settings.agent.framework.value,
            "provider": settings.agent.provider.value,
            "model": settings.agent.model,
            "temperature": settings.agent.temperature,
            "max_tokens": settings.agent.max_tokens,
            "enabled_agents": DEFAULT_AGENTS,
            "use_long_term_memory": settings.agent.enable_long_term_memory,
        }
        if stored:
            base.update(
                {
                    "framework": stored.framework,
                    "provider": stored.provider,
                    "model": stored.model,
                    "temperature": stored.temperature,
                    "max_tokens": stored.max_tokens,
                    "enabled_agents": stored.enabled_agents or DEFAULT_AGENTS,
                    "use_long_term_memory": stored.use_long_term_memory,
                }
            )
        base.update({k: v for k, v in overrides.items() if v is not None})
        return base

    async def ensure_conversation(
        self, *, user_id: str, conversation_id: uuid.UUID | None, config: dict[str, Any], first_message: str
    ) -> Any:
        if conversation_id:
            return await self.conversations.get(conversation_id, user_id)
        title = (first_message[:80] + "...") if len(first_message) > 80 else first_message
        return await self.conversations.create(
            user_id=user_id,
            title=title or "New conversation",
            framework=config["framework"],
            provider=config["provider"],
            model=config["model"],
            config={k: v for k, v in config.items() if k not in ("framework", "provider", "model")},
        )

    async def stream_turn(
        self,
        *,
        user_id: str,
        conversation_id: uuid.UUID | None,
        message: str,
        overrides: dict[str, Any],
        document_ids: list[str] | None = None,
        request_id: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        config = await self.resolve_config(user_id, overrides)
        conversation = await self.ensure_conversation(
            user_id=user_id, conversation_id=conversation_id, config=config, first_message=message
        )
        conv_id = conversation.id

        await self.stm.record_turn(conv_id, role="user", content=message, metadata={"request_id": request_id})

        window = await self.stm.window(conv_id)
        memories: list[dict[str, Any]] = []
        if config.get("use_long_term_memory"):
            memories = await self.ltm.recall(message, user_id=user_id)

        run = await self.runs.start(
            conversation_id=conv_id,
            framework=config["framework"],
            request_id=request_id,
        )
        run_id = run.id
        await self.session.commit()  # the run row must be visible even if the stream dies

        ctx = RunContext(
            conversation_id=conv_id,
            run_id=run_id,
            user_id=user_id,
            message=message,
            history=window[:-1] if window else [],
            long_term_memories=memories,
            summary=conversation.summary,
            document_ids=document_ids or [],
            provider=ModelProvider(config["provider"]),
            model=config["model"],
            temperature=float(config["temperature"]),
            max_tokens=int(config["max_tokens"]),
            enabled_agents=list(config["enabled_agents"]),
            request_id=request_id,
        )

        runtime = get_runtime(config["framework"])
        log.debug("run_start",
                  framework=config["framework"],
                  provider=config["provider"],
                  model=config["model"],
                  temperature=config["temperature"],
                  max_tokens=config["max_tokens"],
                  enabled_agents=config["enabled_agents"],
                  conversation_id=str(conv_id),
                  run_id=str(run_id),
                  message_length=len(message),
                  history_turns=len(window) - 1 if window else 0,
                  memories_recalled=len(memories),
                  document_ids=document_ids or [])
        started = time.perf_counter()
        collected: list[str] = []
        citations: list[dict[str, Any]] = []
        usage: dict[str, int] = {}
        error: str | None = None
        steps_buffer: list[dict[str, Any]] = []

        yield AgentEvent(
            EventType.RUN_STARTED,
            {
                "conversation_id": str(conv_id),
                "run_id": str(run_id),
                "framework": config["framework"],
                "model": f"{config['provider']}/{config['model']}",
                "memories_recalled": len(memories),
            },
            agent="orchestrator",
            run_id=str(run_id),
        )

        try:
            async for event in runtime.stream(ctx):
                if event.type is EventType.RUN_STARTED:
                    continue  # we already emitted a richer one
                # DEBUG: log every event from the runtime
                log.debug("runtime_event",
                          event_type=event.type.value,
                          agent=event.agent,
                          run_id=str(run_id),
                          data_keys=list(event.data.keys()) if event.data else [])
                if event.type is EventType.TOKEN:
                    collected.append(event.data.get("text", ""))
                elif event.type is EventType.CITATION:
                    citations.extend(event.data.get("citations", []))
                elif event.type is EventType.USAGE:
                    for key, value in event.data.items():
                        if isinstance(value, int):
                            usage[key] = usage.get(key, 0) + value
                elif event.type is EventType.ERROR:
                    error = event.data.get("message")
                elif event.type in (EventType.TOOL_CALL, EventType.TOOL_RESULT, EventType.AGENT_FINISHED,
                                    EventType.HANDOFF, EventType.PLAN):
                    steps_buffer.append({"type": event.type.value, "agent": event.agent, **event.data})
                elif event.type is EventType.RUN_FINISHED and not collected and event.data.get("text"):
                    collected.append(event.data["text"])
                yield event
        except Exception as exc:
            log.exception("run_stream_failed", run_id=str(run_id))
            error = f"{type(exc).__name__}: {exc}"[:600]
            yield AgentEvent(EventType.ERROR, {"message": error}, run_id=str(run_id))

        answer = "".join(collected).strip()
        duration_ms = int((time.perf_counter() - started) * 1000)
        total_tokens = sum(v for k, v in usage.items() if k.endswith("tokens"))

        log.debug("run_complete",
                  framework=config["framework"],
                  run_id=str(run_id),
                  duration_ms=duration_ms,
                  total_tokens=total_tokens,
                  answer_length=len(answer),
                  citations_count=len(citations),
                  steps_count=len(steps_buffer),
                  error=error)

        # Send trace to Opik (if enabled).
        _log_to_opik(
            run_id=str(run_id),
            conversation_id=str(conv_id),
            user_message=message,
            answer=answer,
            framework=config["framework"],
            provider=config["provider"],
            model=config["model"],
            steps=steps_buffer,
            usage=usage,
            duration_ms=duration_ms,
            error=error,
        )

        # Persist in a fresh session: the request session may have been rolled
        # back by whatever failed above.
        await self._persist_result(
            conversation_id=conv_id,
            run_id=run_id,
            user_id=user_id,
            answer=answer,
            citations=citations,
            steps=steps_buffer,
            usage=usage,
            error=error,
            duration_ms=duration_ms,
            config=config,
            request_id=request_id,
        )

        yield AgentEvent(
            EventType.RUN_FINISHED,
            {
                "conversation_id": str(conv_id),
                "run_id": str(run_id),
                "duration_ms": duration_ms,
                "total_tokens": total_tokens,
                "citations": citations,
                "error": error,
            },
            agent="orchestrator",
            run_id=str(run_id),
        )

        if answer and not error:
            # Hold a reference: a task with no strong ref can be collected mid-flight.
            task = asyncio.create_task(
                self._post_turn(
                    user_id=user_id,
                    conversation_id=conv_id,
                    user_message=message,
                    assistant_message=answer,
                    config=config,
                )
            )
            _BACKGROUND_TASKS.add(task)
            task.add_done_callback(_BACKGROUND_TASKS.discard)

    async def _persist_result(self, **kw: Any) -> None:
        async with session_scope() as session:
            runs = AgentRunRepository(session)
            stm = ShortTermMemory(session)
            conversations = ConversationRepository(session)
            audit = AuditRepository(session)

            for step in kw["steps"]:
                await runs.add_step(
                    kw["run_id"],
                    agent_name=step.get("agent") or "orchestrator",
                    step_type={"tool_call": "tool", "tool_result": "tool", "handoff": "route",
                               "plan": "route"}.get(step["type"], "agent"),
                    tool_name=step.get("tool"),
                    input={"input": step.get("input"), "plan": step.get("plan"), "to": step.get("to")},
                    output={"output": str(step.get("output", ""))[:4000], "summary": step.get("summary")},
                    status="ok",
                    duration_ms=int(step.get("duration_ms") or 0),
                )

            await runs.finish(
                kw["run_id"],
                status="failed" if kw["error"] else "succeeded",
                error=kw["error"],
                tokens=sum(v for k, v in kw["usage"].items() if k.endswith("tokens")),
            )

            if kw["answer"] or kw["error"]:
                await stm.record_turn(
                    kw["conversation_id"],
                    role="assistant",
                    content=kw["answer"],
                    metadata={
                        "citations": kw["citations"],
                        "run_id": str(kw["run_id"]),
                        "request_id": kw["request_id"],
                        "framework": kw["config"]["framework"],
                        "steps": len(kw["steps"]),
                        "usage": kw["usage"],
                    },
                    framework=kw["config"]["framework"],
                    provider=kw["config"]["provider"],
                    model=kw["config"]["model"],
                    agent_name="orchestrator",
                    prompt_tokens=int(kw["usage"].get("input_tokens", 0)),
                    completion_tokens=int(kw["usage"].get("output_tokens", 0)),
                    latency_ms=kw["duration_ms"],
                    error=kw["error"],
                )

            await conversations.add_usage(
                kw["conversation_id"],
                sum(v for k, v in kw["usage"].items() if k.endswith("tokens")),
                0.0,
            )
            await audit.record(
                action="chat.turn",
                resource_type="conversation",
                resource_id=str(kw["conversation_id"]),
                user_id=kw["user_id"],
                request_id=kw["request_id"],
                outcome="failure" if kw["error"] else "success",
                detail={
                    "run_id": str(kw["run_id"]),
                    "framework": kw["config"]["framework"],
                    "model": kw["config"]["model"],
                    "duration_ms": kw["duration_ms"],
                    "steps": len(kw["steps"]),
                    "error": kw["error"],
                },
            )

    async def _post_turn(
        self, *, user_id: str, conversation_id: uuid.UUID, user_message: str, assistant_message: str,
        config: dict[str, Any]
    ) -> None:
        """Summarise and distil memories. Failures here are logged, never raised."""
        try:
            llm = build_chat_model(
                ModelSpec(
                    provider=ModelProvider(config["provider"]),
                    model=config["model"],
                    temperature=0.0,
                    max_tokens=1024,
                )
            )
            async with session_scope() as session:
                await ShortTermMemory(session).maybe_summarise(conversation_id, llm)
            if config.get("use_long_term_memory"):
                await self.ltm.extract_and_store(
                    llm=llm,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    user_message=user_message,
                    assistant_message=assistant_message,
                    framework=config["framework"],
                )
        except Exception as exc:
            log.warning("post_turn_failed", error=str(exc)[:300], conversation_id=str(conversation_id))


def _log_to_opik(
    *,
    run_id: str,
    conversation_id: str,
    user_message: str,
    answer: str,
    framework: str,
    provider: str,
    model: str,
    steps: list[dict[str, Any]],
    usage: dict[str, int],
    duration_ms: int,
    error: str | None,
) -> None:
    """Log a complete agent run to Opik as a trace with child spans.

    This is called after every conversation turn regardless of which runtime
    ran, so all frameworks get traced in Opik.  Runs in a fire-and-forget
    manner — Opik failures never block the response.
    """
    if not settings.opik_enabled:
        return
    try:
        import opik

        client = opik.Opik(project_name=settings.app_name)

        # Create the parent trace for the entire run.
        trace = client.trace(
            name=f"{framework}/{model}",
            input={"message": user_message},
            output={"answer": answer[:2000]} if answer else {"error": error},
            metadata={
                "framework": framework,
                "provider": provider,
                "model": model,
                "conversation_id": conversation_id,
                "run_id": run_id,
                "duration_ms": duration_ms,
                "total_tokens": sum(v for k, v in usage.items() if k.endswith("tokens")),
            },
            tags=[framework, provider],
        )

        # Log each step (tool call, agent action, handoff) as a child span.
        for i, step in enumerate(steps):
            step_type = step.get("type", "step")
            agent_name = step.get("agent", "unknown")
            tool_name = step.get("tool", "")

            span_name = (
                f"{agent_name}/{tool_name}" if tool_name
                else f"{agent_name}/{step_type}"
            )

            trace.span(
                name=span_name,
                type=step_type,
                input={
                    k: str(v)[:1000] for k, v in step.items()
                    if k in ("input", "plan", "to", "tool")
                },
                output={
                    k: str(v)[:1000] for k, v in step.items()
                    if k in ("output", "summary")
                },
                metadata={
                    "agent": agent_name,
                    "step_index": i,
                    "duration_ms": step.get("duration_ms", 0),
                },
            )

        # Flush to ensure the trace is sent.
        client.flush()

    except Exception as exc:
        log.debug("opik_log_failed", error=str(exc)[:200])
