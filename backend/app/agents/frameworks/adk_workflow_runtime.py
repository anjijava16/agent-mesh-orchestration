"""Google ADK adapter (ADK 2.x) using the *graph Workflow* API.

The existing ``GoogleADKRuntime`` builds a declarative pipeline with
SequentialAgent / ParallelAgent / LoopAgent.  This runtime uses a different
ADK surface: ``google.adk.Workflow`` — an explicit graph where you wire
nodes, edges and conditional routing yourself.

Topology:

    START ─┬─> researcher (Agent, output_key=research_findings) ─┐
           ├─> retriever  (Agent, output_key=retrieved_context)  ├─> data_joiner
           └─> analyst    (Agent, output_key=analysis)           ┘
                                      │
                              classify_and_route   (reads user_message from state)
                                      │
                    ┌─────────────────┼─────────────────┐──────────────┐
                  "tech"          "billing"        "compliance"    "general"
                    │                │                  │               │
            dynamic_troubleshoot  billing_agent   compliance_agent  writer_agent
            (@node loop via       (Agent)         (Agent)           (Agent)
             ctx.run_node)            │
                                  hitl_gate
                                 ┌───┤
                            "approved"│
                          process_approved

Key patterns:

1. **Parallel fan-out + JoinNode** — three Agent nodes (researcher, retriever,
   analyst) run concurrently.  Each has real tools and writes its output into
   session state via ``output_key``.  A JoinNode merges them.
2. **Dynamic classification & routing** — a plain function inspects session
   state and returns ``Event(actions=EventActions(route=...))`` to pick the
   next branch.
3. **Dynamic troubleshooting loop** — a ``@node(rerun_on_resume=True)``
   function calls ``ctx.run_node(agent)`` in a bounded loop.
4. **Billing path with HITL gate** — after the billing specialist responds, a
   gate node checks ``approval_status`` in state.  Missing approval pauses
   the workflow; the next user turn resumes it.
5. **Downstream context** — every leaf agent reads the gathered evidence from
   session state via ``{research_findings?}``, ``{retrieved_context?}``,
   ``{analysis?}`` templates in its instruction.
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

APP_NAME = "agentmesh_workflow"

# State keys the workflow writes.  Cleared before each turn so stale data
# from a previous turn cannot leak into a branch that did not produce it.
WORKFLOW_STATE_KEYS = (
    "research_findings",
    "retrieved_context",
    "analysis",
    "compliance_review",
    "final_answer",
    "user_message",
    "customer_context",
    "troubleshoot_result",
    "billing_response",
    "approval_status",
    "pending_refund",
    "needs_approval",
)

CITATION_RE = re.compile(r"\[[^\]]+ p\.\d+\]")

MAX_TROUBLESHOOT_ATTEMPTS = 2

# Context template injected into every downstream specialist so it can read
# the evidence gathered by the parallel fetchers from session state.
_GATHERED_CONTEXT = (
    "Research findings:\n{research_findings?}\n\n"
    "Retrieved passages:\n{retrieved_context?}\n\n"
    "Analysis:\n{analysis?}"
)


class GoogleADKWorkflowRuntime(AgentRuntime):
    framework = AgentFramework.GOOGLE_ADK_WORKFLOW
    display_name = "Google ADK Graph Workflow"
    description = (
        "Explicit graph Workflow with parallel fan-out + JoinNode, "
        "conditional routing, dynamic troubleshooting loops and HITL gates."
    )

    def __init__(self) -> None:
        self._session_service: Any = None
        self._session_service_is_fallback = False

    def _spec(self, ctx: RunContext) -> ModelSpec:
        return ModelSpec(
            provider=ctx.provider, model=ctx.model,
            temperature=ctx.temperature, max_tokens=ctx.max_tokens,
        )

    # --------------------------------------------------------- build the graph
    def _build_workflow(self, ctx: RunContext) -> Any:
        """Assemble the Workflow graph.

        All ADK Workflow imports live here so a missing ``google.adk`` is caught
        once and surfaced as a clean ``FrameworkNotAvailableError``.
        """
        try:
            from google.adk import Agent, Workflow
            from google.adk.events import Event, EventActions
            from google.adk.workflow import START, JoinNode, node
        except ImportError as exc:  # pragma: no cover
            raise FrameworkNotAvailableError(
                "google-adk >=2.7 with Workflow support is not installed. "
                "`pip install 'google-adk>=2.7.0'`"
            ) from exc

        model = resolve_adk_model(self._spec(ctx))
        enabled = {s.name for s in specs_for(ctx.enabled_agents)}
        memory_block = _brace_safe(ctx.memory_block())

        def _instruction(name: str, extra: str = "") -> str:
            spec = AGENT_SPECS[name]
            parts = [_brace_safe(spec.instruction)]
            if memory_block:
                parts.append(memory_block)
            if extra:
                parts.append(extra)
            return "\n\n".join(parts)

        def _build_agent(name: str, extra: str = "", extra_tools: list[Any] | None = None) -> Agent:
            """Build a real LLM Agent from the spec definitions."""
            spec = AGENT_SPECS[name]
            return Agent(
                name=spec.name,
                model=model,
                description=spec.description,
                instruction=_instruction(name, extra),
                tools=adk_tools(spec.tools) + list(extra_tools or []),
                output_key=spec.output_key or None,
            )

        # ---- 1. Parallel data-gathering agents ----------------------------
        # These are real LLM Agent nodes with tools and output_key.  ADK runs
        # them as full agent turns.  Their output_key writes the result into
        # session state so downstream nodes can read it via {key?} templates.

        researcher_agent = (
            _build_agent("researcher")
            if "researcher" in enabled
            else _noop_agent("researcher", model)
        )
        retriever_agent = (
            _build_agent("retriever")
            if "retriever" in enabled
            else _noop_agent("retriever", model)
        )
        analyst_agent = (
            _build_agent("analyst")
            if "analyst" in enabled
            else _noop_agent("analyst", model)
        )

        # ---- 2. Classifier / Router --------------------------------------
        def classify_and_route(node_input: Any, ctx: Any) -> Any:
            """Inspect user_message in session state and route to the right
            specialist branch.

            Note: the second parameter MUST be named ``ctx`` — ADK's
            FunctionNode resolves it by name when no Context type-annotation
            is present.
            """
            state = ctx.state if hasattr(ctx, "state") else {}
            user_text = (state.get("user_message") or "").lower()

            # Summarise what we gathered for the plan event.
            context_summary = (
                f"Gathered evidence from "
                f"{', '.join(n for n in ('researcher', 'retriever', 'analyst') if n in enabled)}"
            )

            # HITL resume: if approval_status is present, route back to billing.
            if state.get("approval_status") or any(
                kw in user_text for kw in ("refund", "charge", "bill", "invoice", "payment")
            ):
                route = "billing"
            elif any(kw in user_text for kw in ("crash", "error", "bug", "troubleshoot", "broken", "fix", "issue")):
                route = "tech"
            elif any(kw in user_text for kw in ("track", "package", "delivery", "shipping", "order status")):
                route = "compliance"
            else:
                route = "general"

            # Fall back to general if the target's dependency is disabled.
            if route == "tech" and "researcher" not in enabled:
                route = "general"
            if route == "billing" and "analyst" not in enabled:
                route = "general"

            return Event(
                output=context_summary,
                actions=EventActions(route=route),
            )

        # ---- 3. Dynamic troubleshooting loop (@node) ----------------------
        diagnose_agent = Agent(
            name="tech_diagnostician",
            model=model,
            instruction=_instruction(
                "researcher",
                "You are acting as a technical diagnostician. The user has a "
                "technical problem. Suggest ONE specific troubleshooting step "
                "in 1-2 sentences.\n\n" + _GATHERED_CONTEXT,
            ),
        )

        @node(rerun_on_resume=True)
        async def dynamic_troubleshoot(ctx: Any) -> str:
            """Loop up to MAX_TROUBLESHOOT_ATTEMPTS using ctx.run_node,
            then escalate.

            Note: parameter MUST be named ``ctx`` for ADK injection.
            """
            results: list[str] = []
            for attempt in range(1, MAX_TROUBLESHOOT_ATTEMPTS + 1):
                result = await ctx.run_node(diagnose_agent)
                results.append(f"Attempt {attempt}: {result}")
            return (
                "Troubleshooting attempts completed:\n"
                + "\n".join(results)
                + "\nEscalated to Tier-2 support."
            )

        # ---- 4. Billing agent + HITL gate ---------------------------------
        billing_agent = Agent(
            name="billing_specialist",
            model=model,
            instruction=_instruction(
                "analyst",
                "You are the billing specialist. Acknowledge the billing or "
                "refund inquiry empathetically.  If a refund amount is mentioned, "
                "note it. Provide a clear, helpful response.\n\n" + _GATHERED_CONTEXT,
            ),
            output_key="billing_response",
        )

        def check_refund_hitl(node_input: Any, ctx: Any) -> Any:
            """HITL gate: if no approval_status in state, pause for human.

            Note: parameter MUST be named ``ctx`` for ADK injection.
            """
            state = ctx.state if hasattr(ctx, "state") else {}
            already = state.get("approval_status")
            if already == "approved":
                return Event(
                    output="Refund APPROVED by manager.",
                    actions=EventActions(route="approved"),
                )
            if already == "rejected":
                return Event(
                    output="Refund REJECTED by manager.",
                    actions=EventActions(route="rejected"),
                )
            refund_amount = state.get("refund_amount", 0)
            return Event(
                output=f"PAUSED: Requires manager approval for ${refund_amount} refund.",
            )

        def process_approved(node_input: Any) -> str:
            return f"Final billing status: {node_input}"

        # ---- 5. Compliance & general (writer) agents ----------------------
        # Each gets the gathered-context template so it can reason over what
        # the parallel fetchers produced.
        compliance_agent = Agent(
            name="compliance_reviewer",
            model=model,
            instruction=_instruction(
                "compliance",
                "Also handle shipping / tracking inquiries when routed here.\n\n"
                + _GATHERED_CONTEXT,
            ),
            output_key="compliance_review",
        )

        writer_agent = Agent(
            name="writer",
            model=model,
            instruction=_instruction(
                "writer",
                _GATHERED_CONTEXT + "\n\nCompliance review:\n{compliance_review?}",
            ),
            output_key="final_answer",
        )

        # ---- 6. Assemble the Workflow graph --------------------------------
        join = JoinNode(name="data_joiner")

        workflow = Workflow(
            name="agentmesh_graph_workflow",
            edges=[
                # Parallel fan-out from START to real agent fetchers -> join
                (START, researcher_agent, join),
                (START, retriever_agent, join),
                (START, analyst_agent, join),

                # Joined evidence flows into the classifier
                (join, classify_and_route),

                # Conditional routing from classifier
                (classify_and_route, {
                    "tech": dynamic_troubleshoot,
                    "billing": billing_agent,
                    "compliance": compliance_agent,
                    "general": writer_agent,
                }),

                # Billing flows into the HITL gate
                (billing_agent, check_refund_hitl),
                (check_refund_hitl, {
                    "approved": process_approved,
                }),
            ],
        )

        return workflow

    # -------------------------------------------------------- session service
    async def _session_svc(self) -> Any:
        if self._session_service is not None and not self._session_service_is_fallback:
            return self._session_service
        try:
            from google.adk.sessions import DatabaseSessionService

            self._session_service = DatabaseSessionService(db_url=settings.database.async_dsn)
            self._session_service_is_fallback = False
        except Exception as exc:
            log.warning("adk_workflow_database_sessions_unavailable", error=str(exc)[:200])
            from google.adk.sessions import InMemorySessionService

            if self._session_service is None or not self._session_service_is_fallback:
                self._session_service = InMemorySessionService()
            self._session_service_is_fallback = True
        return self._session_service

    # --------------------------------------------------- the streaming heart
    async def stream(self, ctx: RunContext) -> AsyncIterator[AgentEvent]:
        tool_user_id.set(ctx.user_id)
        tool_document_ids.set(tuple(ctx.document_ids))
        run_id = str(ctx.run_id)

        yield AgentEvent(
            EventType.RUN_STARTED, {"framework": self.framework.value},
            agent="orchestrator", run_id=run_id,
        )
        try:
            from google.adk import Runner
            from google.genai import types

            workflow = self._build_workflow(ctx)
            session_service = await self._session_svc()
            session_id = str(ctx.conversation_id)

            # Create or reuse the session.
            existing = await session_service.get_session(
                app_name=APP_NAME, user_id=ctx.user_id, session_id=session_id,
            )
            if existing is None:
                session = await session_service.create_session(
                    app_name=APP_NAME, user_id=ctx.user_id,
                    session_id=session_id, state={},
                )
                session_id = session.id
                if self._session_service_is_fallback:
                    log.warning("adk_workflow_session_not_persisted",
                                conversation_id=session_id)
            else:
                await self._clear_stale_state(session_service, existing)

            # Use node= for Workflow (it is a BaseNode, not a BaseAgent).
            runner = Runner(
                app_name=APP_NAME,
                node=workflow,
                session_service=session_service,
            )

            content = types.Content(
                role="user", parts=[types.Part(text=ctx.message)],
            )
            run_config = _run_config()

            # Inject user_message into session state so the classifier can
            # read it, and history context so agents have conversation memory.
            history_text = _render_history(ctx)
            state_delta: dict[str, Any] = {
                "user_message": ctx.message,
            }
            if history_text:
                state_delta["conversation_history"] = history_text

            yield AgentEvent(
                EventType.PLAN,
                {"plan": [
                    "parallel gather (researcher || retriever || analyst)",
                    "join -> classify & route",
                    "tech -> troubleshoot loop | billing -> HITL gate | "
                    "compliance | general -> writer",
                ]},
                agent="orchestrator", run_id=run_id,
            )

            active: set[str] = set()
            streamed: set[str] = set()
            final_text = ""
            citations: list[dict[str, Any]] = []
            seen_citations: set[tuple[Any, Any, Any]] = set()
            usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            stage_error: str | None = None

            timeout = getattr(settings.agent, "run_timeout_seconds", None)
            stream = runner.run_async(
                user_id=ctx.user_id, session_id=session_id,
                new_message=content, run_config=run_config,
                state_delta=state_delta,
            )

            async for event in _with_timeout(stream, timeout):
                author = getattr(event, "author", None) or "unknown"
                if author not in active:
                    active.add(author)
                    yield AgentEvent(EventType.AGENT_STARTED, {},
                                     agent=author, run_id=run_id)

                # Stage-level errors.
                error_message = getattr(event, "error_message", None)
                error_code = getattr(event, "error_code", None)
                if error_message or error_code:
                    stage_error = (
                        f"{author}: {error_code or 'error'} - "
                        f"{error_message or 'no detail'}"
                    )
                    yield AgentEvent(
                        EventType.ERROR,
                        {"message": stage_error[:600], "code": "stage_error",
                         "agent": author},
                        agent=author, run_id=run_id,
                    )

                # Tool calls.
                for call in _function_calls(event):
                    yield AgentEvent(
                        EventType.TOOL_CALL,
                        {"tool": call.name,
                         "input": dict(call.args or {})},
                        agent=author, run_id=run_id,
                    )

                # Tool results + citation extraction.
                for response in _function_responses(event):
                    raw = response.response
                    for cite in _citations_from(raw):
                        key = (cite.get("filename"), cite.get("page"),
                               cite.get("marker"))
                        if key not in seen_citations:
                            seen_citations.add(key)
                            citations.append(cite)
                    yield AgentEvent(
                        EventType.TOOL_RESULT,
                        {"tool": response.name,
                         "output": _display(raw)},
                        agent=author, run_id=run_id,
                    )

                # Routing events from the classifier.
                actions = getattr(event, "actions", None)
                if actions and getattr(actions, "route", None):
                    yield AgentEvent(
                        EventType.HANDOFF, {"to": actions.route},
                        agent=author, run_id=run_id,
                    )

                # Text / output handling.
                output = getattr(event, "output", None)
                text = _event_text(event)
                is_partial = bool(getattr(event, "partial", False))

                if text and is_partial:
                    streamed.add(author)
                    yield AgentEvent(EventType.TOKEN, {"text": text},
                                     agent=author, run_id=run_id)
                elif text:
                    # The writer or any is_final event is the answer.
                    is_final = (
                        _is_final(event)
                        or author == "writer"
                        or author == "general_specialist"
                    )
                    if is_final:
                        final_text = text
                        if author not in streamed:
                            yield AgentEvent(EventType.TOKEN,
                                             {"text": text},
                                             agent=author, run_id=run_id)
                    else:
                        yield AgentEvent(
                            EventType.AGENT_FINISHED,
                            {"summary": text[:500]},
                            agent=author, run_id=run_id,
                        )
                elif output is not None and not isinstance(output, dict):
                    # Plain-string output from a non-LLM node (HITL gate,
                    # troubleshoot loop, process_approved).
                    output_str = str(output)
                    if not final_text:
                        final_text = output_str
                    yield AgentEvent(
                        EventType.AGENT_FINISHED,
                        {"summary": output_str[:500]},
                        agent=author, run_id=run_id,
                    )

                _accumulate_usage(usage, event)

            # Emit accumulated usage.
            if usage["total_tokens"] or usage["output_tokens"]:
                yield AgentEvent(EventType.USAGE, usage,
                                 agent="orchestrator", run_id=run_id)

            # Emit accumulated citations.
            if citations:
                yield AgentEvent(EventType.CITATION,
                                 {"citations": citations},
                                 agent="retriever", run_id=run_id)

            # Handle missing output.
            if not final_text and stage_error:
                yield AgentEvent(
                    EventType.ERROR,
                    {"message": (
                        "The workflow produced no answer. Last failure: "
                        + stage_error
                    )[:600], "code": "no_output"},
                    agent="orchestrator", run_id=run_id,
                )
                return

            yield AgentEvent(
                EventType.RUN_FINISHED,
                {"text": final_text, "citations": citations},
                agent="orchestrator", run_id=run_id,
            )

        except asyncio.CancelledError:
            raise
        except FrameworkNotAvailableError as exc:
            yield AgentEvent(EventType.ERROR,
                             {"message": exc.message, "code": exc.code},
                             run_id=run_id)
        except asyncio.TimeoutError:
            yield AgentEvent(
                EventType.ERROR,
                {"message": "The workflow exceeded its time budget.",
                 "code": "run_timeout"},
                run_id=run_id,
            )
        except Exception as exc:
            log.exception("adk_workflow_run_failed")
            yield AgentEvent(
                EventType.ERROR,
                {"message": f"{type(exc).__name__}: {exc}"[:600]},
                run_id=run_id,
            )

    # ---------------------------------------------- stale state cleanup
    async def _clear_stale_state(self, session_service: Any,
                                 session: Any) -> None:
        """Clear output keys from the previous turn."""
        state = getattr(session, "state", None) or {}
        stale = {k: "" for k in WORKFLOW_STATE_KEYS if state.get(k)}
        if not stale:
            return
        try:
            from google.adk.events import Event, EventActions

            await session_service.append_event(
                session=session,
                event=Event(
                    author="system",
                    actions=EventActions(state_delta=stale),
                ),
            )
        except Exception as exc:  # pragma: no cover
            log.warning("adk_workflow_state_clear_failed",
                        error=str(exc)[:200])


# ===================================================================
# Module-level helpers
# ===================================================================

def _noop_agent(name: str, model: Any) -> Any:
    """A minimal Agent for a disabled specialist.  It writes an empty string
    into its output_key so downstream templates resolve cleanly."""
    from google.adk import Agent

    spec = AGENT_SPECS[name]
    return Agent(
        name=spec.name,
        model=model,
        instruction="You are disabled for this run. Reply with exactly: N/A",
        output_key=spec.output_key or None,
    )


def _render_history(ctx: RunContext) -> str:
    """Compact the conversation history for injection into session state."""
    if not ctx.history:
        return ""
    lines: list[str] = []
    char_budget = 12_000
    total = 0
    for turn in ctx.history[-12:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if len(content) > 2_000:
            content = content[:2_000] + "..."
        line = f"{role}: {content}"
        total += len(line)
        if total > char_budget:
            break
        lines.append(line)
    return "\n".join(lines)


def _run_config() -> Any:
    """SSE streaming mode so token-level events reach the UI."""
    try:
        from google.adk.agents.run_config import RunConfig, StreamingMode

        return RunConfig(streaming_mode=StreamingMode.SSE)
    except Exception:  # pragma: no cover - older ADK
        return None


async def _with_timeout(stream: AsyncIterator[Any],
                        seconds: float | None) -> AsyncIterator[Any]:
    """Per-event timeout."""
    if not seconds:
        async for item in stream:
            yield item
        return
    iterator = stream.__aiter__()
    while True:
        try:
            item = await asyncio.wait_for(
                iterator.__anext__(), timeout=seconds,
            )
        except StopAsyncIteration:
            return
        yield item


def _brace_safe(text: str) -> str:
    """Neutralise literal braces so ADK's state-template engine does not
    interpret them as key references."""
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
        return bool(
            hasattr(event, "is_final_response") and event.is_final_response()
        )
    except Exception:  # pragma: no cover
        return False


def _accumulate_usage(usage: dict[str, int], event: Any) -> None:
    meta = getattr(event, "usage_metadata", None)
    if meta is None:
        return

    def _field(name: str) -> int:
        try:
            return int(getattr(meta, name, 0) or 0)
        except (TypeError, ValueError):
            return 0

    usage["input_tokens"] += _field("prompt_token_count")
    usage["output_tokens"] += _field("candidates_token_count")
    usage["total_tokens"] += _field("total_token_count")


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
    return "".join(
        part.text for part in content.parts
        if getattr(part, "text", None)
        and not getattr(part, "thought", False)
    )


def _citations_from(raw: Any) -> list[dict[str, Any]]:
    data: Any = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return [
                {"filename": None, "page": None, "marker": m}
                for m in CITATION_RE.findall(raw)
            ]
    if not isinstance(data, dict):
        return []
    return [
        {"filename": p.get("filename"), "page": p.get("page"),
         "marker": p.get("citation")}
        for p in (data.get("passages") or [])
        if isinstance(p, dict)
    ]
