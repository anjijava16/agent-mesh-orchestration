"""Google ADK adapter (ADK 2.x) using the workflow agents.

ADK's differentiator is that orchestration is *declarative*: you compose
SequentialAgent / ParallelAgent / LoopAgent rather than writing routing code.
The pipeline we build here:

    SequentialAgent "agentmesh_pipeline"
      1. ParallelAgent "discovery"     -> researcher || retriever
      2. LlmAgent      "analyst"
      3. LoopAgent     "review_cycle"  -> compliance -> writer, max 2 iterations
                                          (compliance calls exit_review to break
                                           the loop)

State flows through `output_key`: each agent writes its result into the session
state under a named key, and the next agent's instruction interpolates it with
{key} templating. That is ADK's answer to message passing.

Three consequences of that design drive the code below:

1. A LoopAgent only terminates early when a sub-agent sets
   `tool_context.actions.escalate`. Telling compliance to "reply PASS" in its
   instruction does nothing - the loop runs its full budget regardless. So
   compliance gets a real `exit_review` tool.
2. Instruction strings are templated. Any literal brace in a memory block or a
   spec instruction is parsed as a state key and raises at render time, so
   untrusted text is brace-sanitised before it goes in.
3. Sessions persist per conversation, which means state keys survive between
   turns. Last turn's `research_findings` is still sitting there when this turn
   starts, so the pipeline's output keys are cleared before each run.

Session persistence uses ADK 2.x's async DatabaseSessionService pointed at the
same Postgres instance, so ADK's own session rows sit alongside our tables.
"""
from __future__ import annotations

import asyncio
import json
import re
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

# Output keys the pipeline writes. Cleared at the start of every run so a stage
# cannot read a value left behind by the previous turn.
PIPELINE_STATE_KEYS = ("research_findings", "retrieved_context", "analysis", "compliance_review", "final_answer")

CITATION_RE = re.compile(r"\[[^\]]+ p\.\d+\]")


class GoogleADKRuntime(AgentRuntime):
    framework = AgentFramework.GOOGLE_ADK
    display_name = "Google ADK Workflows"
    description = "Declarative Sequential / Parallel / Loop workflow agents with session state hand-off."

    def __init__(self) -> None:
        self._session_service: Any = None
        self._session_service_is_fallback = False

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
        memory_block = _brace_safe(ctx.memory_block())

        def instruction_for(name: str, extra: str = "") -> str:
            spec = AGENT_SPECS[name]
            # Spec instructions and memory are literal text; only `extra` is
            # allowed to carry {state_key} templates.
            parts = [_brace_safe(spec.instruction)]
            if memory_block:
                parts.append(memory_block)
            if extra:
                parts.append(extra)
            return "\n\n".join(parts)

        def build(name: str, extra: str = "", extra_tools: list[Any] | None = None) -> Any:
            spec = AGENT_SPECS[name]
            return LlmAgent(
                name=spec.name,
                model=model,
                description=spec.description,
                instruction=instruction_for(name, extra),
                tools=adk_tools(spec.tools) + list(extra_tools or []),
                output_key=spec.output_key,
            )

        stages: list[Any] = []

        # 1. Discovery runs the two independent gatherers concurrently. They
        #    share one session state, so this is only safe because their
        #    output_keys differ - ParallelAgent isolates event branches, not state.
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

        # 3. Review cycle. compliance calls exit_review when the draft passes,
        #    which sets escalate and terminates the LoopAgent early. Without a
        #    tool that flips that flag the loop always burns its full budget.
        review_stages = []
        if "compliance" in enabled:
            review_stages.append(
                build(
                    "compliance",
                    "Draft under review:\n{final_answer?}\n\nSupporting material:\n{retrieved_context?}\n"
                    "{analysis?}\n\nIf the draft is acceptable, call the exit_review tool and say nothing "
                    "else. If it is not, list the specific problems for the writer to fix.",
                    extra_tools=[_exit_review_tool()],
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
                    max_iterations=getattr(settings.agent, "max_review_iterations", 2),
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
        if self._session_service is not None and not self._session_service_is_fallback:
            return self._session_service
        try:
            from google.adk.sessions import DatabaseSessionService

            # ADK 2.x accepts an async driver URL directly.
            self._session_service = DatabaseSessionService(db_url=settings.database.async_dsn)
            self._session_service_is_fallback = False
        except Exception as exc:
            # Do not cache this permanently - a transient DB outage should not
            # downgrade the whole process to in-memory sessions for its lifetime.
            log.warning("adk_database_sessions_unavailable", error=str(exc)[:200])
            from google.adk.sessions import InMemorySessionService

            if self._session_service is None or not self._session_service_is_fallback:
                self._session_service = InMemorySessionService()
            self._session_service_is_fallback = True
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
                if self._session_service_is_fallback:
                    log.warning("adk_session_not_persisted", conversation_id=session_id)
            else:
                await self._clear_stale_state(session_service, ctx, session_id, existing)

            runner = Runner(app_name=APP_NAME, agent=pipeline, session_service=session_service)
            content = types.Content(role="user", parts=[types.Part(text=ctx.message)])
            run_config = _run_config()

            yield AgentEvent(
                EventType.PLAN,
                {"plan": ["discovery (researcher || retriever)", "analyst", "review_cycle (compliance -> writer)"]},
                agent="orchestrator", run_id=run_id,
            )

            active: set[str] = set()
            streamed: set[str] = set()   # authors whose text already went out as partials
            final_text = ""
            citations: list[dict[str, Any]] = []
            seen_citations: set[tuple[Any, Any, Any]] = set()
            usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            stage_error: str | None = None

            timeout = getattr(settings.agent, "run_timeout_seconds", None)
            stream = runner.run_async(
                user_id=ctx.user_id, session_id=session_id, new_message=content, run_config=run_config
            )

            async for event in _with_timeout(stream, timeout):
                author = getattr(event, "author", None) or "unknown"
                if author not in active:
                    active.add(author)
                    yield AgentEvent(EventType.AGENT_STARTED, {}, agent=author, run_id=run_id)

                # ADK reports per-stage model failures on the event rather than
                # raising. Left unchecked, a failed stage looks like empty output.
                error_message = getattr(event, "error_message", None)
                error_code = getattr(event, "error_code", None)
                if error_message or error_code:
                    stage_error = f"{author}: {error_code or 'error'} - {error_message or 'no detail'}"
                    yield AgentEvent(
                        EventType.ERROR,
                        {"message": stage_error[:600], "code": "stage_error", "agent": author},
                        agent=author, run_id=run_id,
                    )

                for call in _function_calls(event):
                    if call.name == "exit_review":
                        continue  # control-flow tool, not user-visible work
                    yield AgentEvent(
                        EventType.TOOL_CALL, {"tool": call.name, "input": dict(call.args or {})},
                        agent=author, run_id=run_id,
                    )

                for response in _function_responses(event):
                    if response.name == "exit_review":
                        continue
                    raw = response.response
                    # Citations come from the *full* payload; truncation is for
                    # display only. Parsing a clipped string never yields JSON.
                    for cite in _citations_from(raw):
                        key = (cite.get("filename"), cite.get("page"), cite.get("marker"))
                        if key not in seen_citations:
                            seen_citations.add(key)
                            citations.append(cite)
                    yield AgentEvent(
                        EventType.TOOL_RESULT, {"tool": response.name, "output": _display(raw)},
                        agent=author, run_id=run_id,
                    )

                text = _event_text(event)
                is_partial = bool(getattr(event, "partial", False))

                if text and is_partial:
                    streamed.add(author)
                    yield AgentEvent(EventType.TOKEN, {"text": text}, agent=author, run_id=run_id)
                elif text:
                    is_final = author == "writer" or _is_final(event)
                    if is_final:
                        final_text = text
                        # Non-streaming models emit only the complete message,
                        # so send it as a token if nothing streamed already.
                        if author not in streamed:
                            yield AgentEvent(EventType.TOKEN, {"text": text}, agent=author, run_id=run_id)
                    else:
                        yield AgentEvent(EventType.AGENT_FINISHED, {"summary": text[:500]}, agent=author,
                                         run_id=run_id)

                _accumulate_usage(usage, event)

            if usage["total_tokens"] or usage["output_tokens"]:
                yield AgentEvent(EventType.USAGE, usage, agent="orchestrator", run_id=run_id)

            if citations:
                yield AgentEvent(EventType.CITATION, {"citations": citations}, agent="retriever", run_id=run_id)

            if not final_text and stage_error:
                yield AgentEvent(
                    EventType.ERROR,
                    {"message": f"The pipeline produced no answer. Last failure: {stage_error}"[:600],
                     "code": "no_output"},
                    agent="orchestrator", run_id=run_id,
                )
                return

            yield AgentEvent(EventType.RUN_FINISHED, {"text": final_text, "citations": citations},
                             agent="orchestrator", run_id=run_id)

        except asyncio.CancelledError:
            raise
        except FrameworkNotAvailableError as exc:
            yield AgentEvent(EventType.ERROR, {"message": exc.message, "code": exc.code}, run_id=run_id)
        except asyncio.TimeoutError:
            yield AgentEvent(
                EventType.ERROR,
                {"message": "The pipeline exceeded its time budget.", "code": "run_timeout"},
                run_id=run_id,
            )
        except Exception as exc:
            log.exception("adk_run_failed")
            yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]}, run_id=run_id)

    async def _clear_stale_state(self, session_service: Any, ctx: RunContext, session_id: str,
                                 session: Any) -> None:
        """Sessions persist per conversation, so last turn's output keys are still
        present. An analyst reading {research_findings?} would otherwise pick up
        stale evidence when the researcher is disabled this turn."""
        state = getattr(session, "state", None) or {}
        stale = {k: "" for k in PIPELINE_STATE_KEYS if state.get(k)}
        if not stale:
            return
        try:
            from google.adk.events import Event, EventActions

            await session_service.append_event(
                session=session,
                event=Event(author="system", actions=EventActions(state_delta=stale)),
            )
        except Exception as exc:  # pragma: no cover - version differences
            log.warning("adk_state_clear_failed", error=str(exc)[:200])


def _exit_review_tool() -> Any:
    """A LoopAgent stops early only when a sub-agent sets escalate. This is the
    tool that does it - the instruction alone cannot break the loop."""
    from google.adk.tools import FunctionTool, ToolContext

    # `from __future__ import annotations` stores the annotation below as the
    # string "ToolContext". ADK resolves it via get_type_hints() against this
    # function's module globals, so ToolContext must live there.
    globals()["ToolContext"] = ToolContext

    def exit_review(tool_context: ToolContext) -> dict[str, str]:
        """Approve the draft and end the review cycle. Call only when the draft
        needs no further changes."""
        tool_context.actions.escalate = True
        return {"status": "approved"}

    return FunctionTool(func=exit_review)


def _run_config() -> Any:
    """Token streaming needs SSE mode; without it text arrives only as whole
    messages and the UI sits blank until a stage completes."""
    try:
        from google.adk.agents.run_config import RunConfig, StreamingMode

        return RunConfig(streaming_mode=StreamingMode.SSE)
    except Exception:  # pragma: no cover - older ADK
        return None


async def _with_timeout(stream: AsyncIterator[Any], seconds: float | None) -> AsyncIterator[Any]:
    """Per-event timeout. A whole-run budget would kill long legitimate
    pipelines; this catches a stalled provider."""
    if not seconds:
        async for item in stream:
            yield item
        return
    iterator = stream.__aiter__()
    while True:
        try:
            item = await asyncio.wait_for(iterator.__anext__(), timeout=seconds)
        except StopAsyncIteration:
            return
        yield item


def _brace_safe(text: str) -> str:
    """ADK renders instructions through state templating, so a literal brace in
    a memory block or spec instruction is read as a state key and blows up at
    render time. Neutralise braces in anything we did not author as a template."""
    if not text:
        return ""
    return text.replace("{", "(").replace("}", ")")


def _function_calls(event: Any) -> list[Any]:
    if not hasattr(event, "get_function_calls"):
        return []
    try:
        return list(event.get_function_calls() or [])
    except Exception:  # pragma: no cover
        return []


def _function_responses(event: Any) -> list[Any]:
    if not hasattr(event, "get_function_responses"):
        return []
    try:
        return list(event.get_function_responses() or [])
    except Exception:  # pragma: no cover
        return []


def _is_final(event: Any) -> bool:
    try:
        return bool(hasattr(event, "is_final_response") and event.is_final_response())
    except Exception:  # pragma: no cover
        return False


def _accumulate_usage(usage: dict[str, int], event: Any) -> None:
    meta = getattr(event, "usage_metadata", None)
    if meta is None:
        return

    def field(name: str) -> int:
        try:
            return int(getattr(meta, name, 0) or 0)
        except (TypeError, ValueError):
            return 0

    usage["input_tokens"] += field("prompt_token_count")
    usage["output_tokens"] += field("candidates_token_count")
    usage["total_tokens"] += field("total_token_count")


def _display(raw: Any) -> str:
    if isinstance(raw, (dict, list)):
        try:
            return json.dumps(raw)[:800]
        except (TypeError, ValueError):
            return str(raw)[:800]
    return str(raw)[:800]


def _event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    if not content or not getattr(content, "parts", None):
        return ""
    # Thought parts are model scratchpad, not answer text.
    return "".join(
        part.text for part in content.parts
        if getattr(part, "text", None) and not getattr(part, "thought", False)
    )


def _citations_from(raw: Any) -> list[dict[str, Any]]:
    """Tool responses arrive as dicts far more often than as JSON strings, and
    str(dict) is Python repr, not JSON - parsing that always failed."""
    data: Any = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return [{"filename": None, "page": None, "marker": m} for m in CITATION_RE.findall(raw)]

    if not isinstance(data, dict):
        return []
    return [
        {"filename": p.get("filename"), "page": p.get("page"), "marker": p.get("citation")}
        for p in (data.get("passages") or [])
        if isinstance(p, dict)
    ]
# """Google ADK adapter (ADK 2.x) using the workflow agents.

# ADK's differentiator is that orchestration is *declarative*: you compose
# SequentialAgent / ParallelAgent / LoopAgent rather than writing routing code.
# The pipeline we build here:

#     SequentialAgent "agentmesh_pipeline"
#       1. ParallelAgent "discovery"     -> researcher || retriever
#       2. LlmAgent      "analyst"
#       3. LoopAgent     "review_cycle"  -> compliance -> writer, max 2 iterations
#                                           (compliance escalates to break the loop)

# State flows through `output_key`: each agent writes its result into the session
# state under a named key, and the next agent's instruction interpolates it with
# {key} templating. That is ADK's answer to message passing.

# Session persistence uses ADK 2.x's async DatabaseSessionService pointed at the
# same Postgres instance, so ADK's own session rows sit alongside our tables.
# """
# from __future__ import annotations

# from collections.abc import AsyncIterator
# from typing import Any

# from app.agents.base import AgentEvent, AgentRuntime, EventType, RunContext
# from app.agents.definitions import AGENT_SPECS, ORCHESTRATOR_INSTRUCTION, specs_for
# from app.agents.tools.adapters import adk_tools
# from app.agents.tools.core import tool_document_ids, tool_user_id
# from app.config import AgentFramework, settings
# from app.core.errors import FrameworkNotAvailableError
# from app.core.logging import get_logger
# from app.llm.registry import ModelSpec, resolve_adk_model

# log = get_logger(__name__)

# APP_NAME = "agentmesh"


# class GoogleADKRuntime(AgentRuntime):
#     framework = AgentFramework.GOOGLE_ADK
#     display_name = "Google ADK Workflows"
#     description = "Declarative Sequential / Parallel / Loop workflow agents with session state hand-off."

#     def __init__(self) -> None:
#         self._session_service: Any = None

#     def _spec(self, ctx: RunContext) -> ModelSpec:
#         return ModelSpec(provider=ctx.provider, model=ctx.model, temperature=ctx.temperature,
#                          max_tokens=ctx.max_tokens)

#     def _build_pipeline(self, ctx: RunContext) -> Any:
#         try:
#             from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent
#         except ImportError as exc:  # pragma: no cover
#             raise FrameworkNotAvailableError(
#                 "google-adk is not installed. `pip install 'google-adk>=2.0.0'`"
#             ) from exc

#         model = resolve_adk_model(self._spec(ctx))
#         enabled = {s.name for s in specs_for(ctx.enabled_agents)}
#         memory_block = ctx.memory_block()

#         def instruction_for(name: str, extra: str = "") -> str:
#             spec = AGENT_SPECS[name]
#             parts = [spec.instruction]
#             if memory_block:
#                 parts.append(memory_block)
#             if extra:
#                 parts.append(extra)
#             return "\n\n".join(parts)

#         def build(name: str, extra: str = "") -> Any:
#             spec = AGENT_SPECS[name]
#             return LlmAgent(
#                 name=spec.name,
#                 model=model,
#                 description=spec.description,
#                 instruction=instruction_for(name, extra),
#                 tools=adk_tools(spec.tools),
#                 output_key=spec.output_key,
#             )

#         stages: list[Any] = []

#         # 1. Discovery runs the two independent gatherers concurrently. ADK's
#         #    ParallelAgent gives each branch an isolated invocation context, so
#         #    they cannot clobber each other's state keys.
#         discovery_branches = [build(n) for n in ("researcher", "retriever") if n in enabled]
#         if discovery_branches:
#             stages.append(
#                 ParallelAgent(
#                     name="discovery",
#                     description="Gathers external and corpus evidence at the same time.",
#                     sub_agents=discovery_branches,
#                 )
#             )

#         # 2. Analysis reads both discovery outputs from session state.
#         if "analyst" in enabled:
#             stages.append(
#                 build(
#                     "analyst",
#                     "Research findings:\n{research_findings?}\n\nRetrieved passages:\n{retrieved_context?}",
#                 )
#             )

#         # 3. Review cycle. compliance sets escalate when the draft passes, which
#         #    is how a LoopAgent terminates early instead of burning its budget.
#         review_stages = []
#         if "compliance" in enabled:
#             review_stages.append(
#                 build(
#                     "compliance",
#                     "Draft under review:\n{final_answer?}\n\nSupporting material:\n{retrieved_context?}\n"
#                     "{analysis?}\n\nIf the draft is acceptable, reply with PASS and nothing else.",
#                 )
#             )
#         if "writer" in enabled:
#             review_stages.append(
#                 build(
#                     "writer",
#                     "Research:\n{research_findings?}\n\nPassages:\n{retrieved_context?}\n\n"
#                     "Analysis:\n{analysis?}\n\nReviewer notes:\n{compliance_review?}",
#                 )
#             )
#         if review_stages:
#             stages.append(
#                 LoopAgent(
#                     name="review_cycle",
#                     description="Compliance review followed by composition, up to two passes.",
#                     sub_agents=review_stages,
#                     max_iterations=2,
#                 )
#             )

#         if not stages:
#             stages = [build("writer")]

#         return SequentialAgent(
#             name="agentmesh_pipeline",
#             description=ORCHESTRATOR_INSTRUCTION[:900],
#             sub_agents=stages,
#         )

#     async def _session_svc(self) -> Any:
#         if self._session_service is not None:
#             return self._session_service
#         try:
#             from google.adk.sessions import DatabaseSessionService

#             # ADK 2.x accepts an async driver URL directly.
#             self._session_service = DatabaseSessionService(db_url=settings.database.async_dsn)
#         except Exception as exc:
#             log.warning("adk_database_sessions_unavailable", error=str(exc)[:200])
#             from google.adk.sessions import InMemorySessionService

#             self._session_service = InMemorySessionService()
#         return self._session_service

#     async def stream(self, ctx: RunContext) -> AsyncIterator[AgentEvent]:
#         tool_user_id.set(ctx.user_id)
#         tool_document_ids.set(tuple(ctx.document_ids))
#         run_id = str(ctx.run_id)

#         yield AgentEvent(EventType.RUN_STARTED, {"framework": self.framework.value}, agent="orchestrator",
#                          run_id=run_id)
#         try:
#             from google.adk.runners import Runner
#             from google.genai import types

#             pipeline = self._build_pipeline(ctx)
#             session_service = await self._session_svc()
#             session_id = str(ctx.conversation_id)

#             existing = await session_service.get_session(
#                 app_name=APP_NAME, user_id=ctx.user_id, session_id=session_id
#             )
#             if existing is None:
#                 session = await session_service.create_session(
#                     app_name=APP_NAME, user_id=ctx.user_id, session_id=session_id, state={}
#                 )
#                 session_id = session.id

#             runner = Runner(app_name=APP_NAME, agent=pipeline, session_service=session_service)
#             content = types.Content(role="user", parts=[types.Part(text=ctx.message)])

#             yield AgentEvent(
#                 EventType.PLAN,
#                 {"plan": ["discovery (researcher || retriever)", "analyst", "review_cycle (compliance -> writer)"]},
#                 agent="orchestrator", run_id=run_id,
#             )

#             active: set[str] = set()
#             final_text = ""
#             citations: list[dict[str, Any]] = []

#             async for event in runner.run_async(
#                 user_id=ctx.user_id, session_id=session_id, new_message=content
#             ):
#                 author = getattr(event, "author", None) or "unknown"
#                 if author not in active:
#                     active.add(author)
#                     yield AgentEvent(EventType.AGENT_STARTED, {}, agent=author, run_id=run_id)

#                 for call in (event.get_function_calls() or []) if hasattr(event, "get_function_calls") else []:
#                     yield AgentEvent(
#                         EventType.TOOL_CALL, {"tool": call.name, "input": dict(call.args or {})},
#                         agent=author, run_id=run_id,
#                     )
#                 responses = event.get_function_responses() or [] if hasattr(event, "get_function_responses") else []
#                 for response in responses:
#                     payload = str(response.response)[:800]
#                     yield AgentEvent(
#                         EventType.TOOL_RESULT, {"tool": response.name, "output": payload},
#                         agent=author, run_id=run_id,
#                     )
#                     citations.extend(_citations_from(payload))

#                 text = _event_text(event)
#                 if text:
#                     if author == "writer" or (hasattr(event, "is_final_response") and event.is_final_response()):
#                         final_text = text
#                         yield AgentEvent(EventType.TOKEN, {"text": text}, agent=author, run_id=run_id)
#                     else:
#                         yield AgentEvent(EventType.AGENT_FINISHED, {"summary": text[:500]}, agent=author,
#                                          run_id=run_id)

#                 usage = getattr(getattr(event, "usage_metadata", None), "total_token_count", None)
#                 if usage:
#                     yield AgentEvent(EventType.USAGE, {"total_tokens": int(usage)}, agent=author, run_id=run_id)

#             if citations:
#                 yield AgentEvent(EventType.CITATION, {"citations": citations}, agent="retriever", run_id=run_id)
#             yield AgentEvent(EventType.RUN_FINISHED, {"text": final_text, "citations": citations},
#                              agent="orchestrator", run_id=run_id)

#         except FrameworkNotAvailableError as exc:
#             yield AgentEvent(EventType.ERROR, {"message": exc.message, "code": exc.code}, run_id=run_id)
#         except Exception as exc:
#             log.exception("adk_run_failed")
#             yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]}, run_id=run_id)


# def _event_text(event: Any) -> str:
#     content = getattr(event, "content", None)
#     if not content or not getattr(content, "parts", None):
#         return ""
#     return "".join(part.text for part in content.parts if getattr(part, "text", None))


# def _citations_from(payload: str) -> list[dict[str, Any]]:
#     import json
#     import re

#     try:
#         data = json.loads(payload)
#     except json.JSONDecodeError:
#         return [{"marker": m} for m in re.findall(r"\[[^\]]+ p\.\d+\]", payload)]
#     return [
#         {"filename": p.get("filename"), "page": p.get("page"), "marker": p.get("citation")}
#         for p in (data.get("passages") or [])
#         if isinstance(p, dict)
#     ]
