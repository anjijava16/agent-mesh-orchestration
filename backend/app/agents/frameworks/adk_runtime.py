"""Google ADK adapter (ADK 2.x) using the workflow agents.

ADK's differentiator is that orchestration is *declarative*: you compose
SequentialAgent / ParallelAgent / LoopAgent rather than writing routing code.
The pipeline we build here:

    SequentialAgent "agentmesh_pipeline"
      1. ParallelAgent "discovery"     -> researcher || retriever
      2. LlmAgent      "analyst"
      3. LoopAgent     "review_cycle"  -> compliance -> writer, max 2 iterations
                                          (compliance escalates to break the loop)

State flows through `output_key`: each agent writes its result into the session
state under a named key, and the next agent's instruction interpolates it with
{key} templating. That is ADK's answer to message passing.

Session persistence uses ADK 2.x's async DatabaseSessionService pointed at the
same Postgres instance, so ADK's own session rows sit alongside our tables.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import AgentEvent, AgentRuntime, EventType, RunContext
from app.agents.definitions import AGENT_SPECS, ORCHESTRATOR_INSTRUCTION, specs_for
from app.agents.tools.adapters import adk_tools
from app.agents.tools.core import tool_document_ids, tool_user_id
from app.config import AgentFramework, settings
from app.core.errors import FrameworkNotAvailableError
from app.core.logging import get_logger
from app.llm.registry import ModelSpec, resolve_adk_model

log = get_logger(__name__)

APP_NAME = "agentmesh"


class GoogleADKRuntime(AgentRuntime):
    framework = AgentFramework.GOOGLE_ADK
    display_name = "Google ADK Workflows"
    description = "Declarative Sequential / Parallel / Loop workflow agents with session state hand-off."

    def __init__(self) -> None:
        self._session_service: Any = None

    def _spec(self, ctx: RunContext) -> ModelSpec:
        return ModelSpec(provider=ctx.provider, model=ctx.model, temperature=ctx.temperature,
                         max_tokens=ctx.max_tokens)

    def _build_pipeline(self, ctx: RunContext) -> Any:
        try:
            from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent
        except ImportError as exc:  # pragma: no cover
            raise FrameworkNotAvailableError(
                "google-adk is not installed. `pip install 'google-adk>=2.0.0'`"
            ) from exc

        model = resolve_adk_model(self._spec(ctx))
        enabled = {s.name for s in specs_for(ctx.enabled_agents)}
        memory_block = ctx.memory_block()

        def instruction_for(name: str, extra: str = "") -> str:
            spec = AGENT_SPECS[name]
            parts = [spec.instruction]
            if memory_block:
                parts.append(memory_block)
            if extra:
                parts.append(extra)
            return "\n\n".join(parts)

        def build(name: str, extra: str = "") -> Any:
            spec = AGENT_SPECS[name]
            return LlmAgent(
                name=spec.name,
                model=model,
                description=spec.description,
                instruction=instruction_for(name, extra),
                tools=adk_tools(spec.tools),
                output_key=spec.output_key,
            )

        stages: list[Any] = []

        # 1. Discovery runs the two independent gatherers concurrently. ADK's
        #    ParallelAgent gives each branch an isolated invocation context, so
        #    they cannot clobber each other's state keys.
        discovery_branches = [build(n) for n in ("researcher", "retriever") if n in enabled]
        if discovery_branches:
            stages.append(
                ParallelAgent(
                    name="discovery",
                    description="Gathers external and corpus evidence at the same time.",
                    sub_agents=discovery_branches,
                )
            )

        # 2. Analysis reads both discovery outputs from session state.
        if "analyst" in enabled:
            stages.append(
                build(
                    "analyst",
                    "Research findings:\n{research_findings?}\n\nRetrieved passages:\n{retrieved_context?}",
                )
            )

        # 3. Review cycle. compliance sets escalate when the draft passes, which
        #    is how a LoopAgent terminates early instead of burning its budget.
        review_stages = []
        if "compliance" in enabled:
            review_stages.append(
                build(
                    "compliance",
                    "Draft under review:\n{final_answer?}\n\nSupporting material:\n{retrieved_context?}\n"
                    "{analysis?}\n\nIf the draft is acceptable, reply with PASS and nothing else.",
                )
            )
        if "writer" in enabled:
            review_stages.append(
                build(
                    "writer",
                    "Research:\n{research_findings?}\n\nPassages:\n{retrieved_context?}\n\n"
                    "Analysis:\n{analysis?}\n\nReviewer notes:\n{compliance_review?}",
                )
            )
        if review_stages:
            stages.append(
                LoopAgent(
                    name="review_cycle",
                    description="Compliance review followed by composition, up to two passes.",
                    sub_agents=review_stages,
                    max_iterations=2,
                )
            )

        if not stages:
            stages = [build("writer")]

        return SequentialAgent(
            name="agentmesh_pipeline",
            description=ORCHESTRATOR_INSTRUCTION[:900],
            sub_agents=stages,
        )

    async def _session_svc(self) -> Any:
        if self._session_service is not None:
            return self._session_service
        try:
            from google.adk.sessions import DatabaseSessionService

            # ADK 2.x accepts an async driver URL directly.
            self._session_service = DatabaseSessionService(db_url=settings.database.async_dsn)
        except Exception as exc:
            log.warning("adk_database_sessions_unavailable", error=str(exc)[:200])
            from google.adk.sessions import InMemorySessionService

            self._session_service = InMemorySessionService()
        return self._session_service

    async def stream(self, ctx: RunContext) -> AsyncIterator[AgentEvent]:
        tool_user_id.set(ctx.user_id)
        tool_document_ids.set(tuple(ctx.document_ids))
        run_id = str(ctx.run_id)

        yield AgentEvent(EventType.RUN_STARTED, {"framework": self.framework.value}, agent="orchestrator",
                         run_id=run_id)
        try:
            from google.adk.runners import Runner
            from google.genai import types

            pipeline = self._build_pipeline(ctx)
            session_service = await self._session_svc()
            session_id = str(ctx.conversation_id)

            existing = await session_service.get_session(
                app_name=APP_NAME, user_id=ctx.user_id, session_id=session_id
            )
            if existing is None:
                session = await session_service.create_session(
                    app_name=APP_NAME, user_id=ctx.user_id, session_id=session_id, state={}
                )
                session_id = session.id

            runner = Runner(app_name=APP_NAME, agent=pipeline, session_service=session_service)
            content = types.Content(role="user", parts=[types.Part(text=ctx.message)])

            yield AgentEvent(
                EventType.PLAN,
                {"plan": ["discovery (researcher || retriever)", "analyst", "review_cycle (compliance -> writer)"]},
                agent="orchestrator", run_id=run_id,
            )

            active: set[str] = set()
            final_text = ""
            citations: list[dict[str, Any]] = []

            async for event in runner.run_async(
                user_id=ctx.user_id, session_id=session_id, new_message=content
            ):
                author = getattr(event, "author", None) or "unknown"
                if author not in active:
                    active.add(author)
                    yield AgentEvent(EventType.AGENT_STARTED, {}, agent=author, run_id=run_id)

                for call in (event.get_function_calls() or []) if hasattr(event, "get_function_calls") else []:
                    yield AgentEvent(
                        EventType.TOOL_CALL, {"tool": call.name, "input": dict(call.args or {})},
                        agent=author, run_id=run_id,
                    )
                responses = event.get_function_responses() or [] if hasattr(event, "get_function_responses") else []
                for response in responses:
                    payload = str(response.response)[:800]
                    yield AgentEvent(
                        EventType.TOOL_RESULT, {"tool": response.name, "output": payload},
                        agent=author, run_id=run_id,
                    )
                    citations.extend(_citations_from(payload))

                text = _event_text(event)
                if text:
                    if author == "writer" or (hasattr(event, "is_final_response") and event.is_final_response()):
                        final_text = text
                        yield AgentEvent(EventType.TOKEN, {"text": text}, agent=author, run_id=run_id)
                    else:
                        yield AgentEvent(EventType.AGENT_FINISHED, {"summary": text[:500]}, agent=author,
                                         run_id=run_id)

                usage = getattr(getattr(event, "usage_metadata", None), "total_token_count", None)
                if usage:
                    yield AgentEvent(EventType.USAGE, {"total_tokens": int(usage)}, agent=author, run_id=run_id)

            if citations:
                yield AgentEvent(EventType.CITATION, {"citations": citations}, agent="retriever", run_id=run_id)
            yield AgentEvent(EventType.RUN_FINISHED, {"text": final_text, "citations": citations},
                             agent="orchestrator", run_id=run_id)

        except FrameworkNotAvailableError as exc:
            yield AgentEvent(EventType.ERROR, {"message": exc.message, "code": exc.code}, run_id=run_id)
        except Exception as exc:
            log.exception("adk_run_failed")
            yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]}, run_id=run_id)


def _event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    if not content or not getattr(content, "parts", None):
        return ""
    return "".join(part.text for part in content.parts if getattr(part, "text", None))


def _citations_from(payload: str) -> list[dict[str, Any]]:
    import json
    import re

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return [{"marker": m} for m in re.findall(r"\[[^\]]+ p\.\d+\]", payload)]
    return [
        {"filename": p.get("filename"), "page": p.get("page"), "marker": p.get("citation")}
        for p in (data.get("passages") or [])
        if isinstance(p, dict)
    ]
