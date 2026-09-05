"""LangGraph adapter - explicit supervisor graph over the five specialists.

Topology:

    entry -> supervisor -> {researcher, retriever} (parallel fan-out)
                        -> analyst      (conditional: numbers present)
                        -> compliance   (conditional: draft exists)
                        -> writer -> END

The supervisor is a real node with a structured-output router, not a prompt that
"decides" in free text. Structured routing is the difference between a graph you
can test and one you can only observe.

Two things about this shape are easy to get wrong and are handled explicitly
below:

1. A tool-calling turn is only valid if *every* tool_call id in the assistant
   message gets a matching tool message back. Skipping an unresolvable or
   failing call leaves a dangling id and the next provider call rejects the
   whole conversation.
2. `final_state.update(update)` overwrites reducer-managed keys with whatever
   the last node returned. Citations accumulate across nodes in the graph state
   but not in a dict you build by updating, so they are accumulated separately
   here.
"""
from __future__ import annotations

import asyncio
import json
import operator
import time
from collections.abc import AsyncIterator, Sequence
from typing import Annotated, Any, Literal, TypedDict

from app.agents.base import AgentEvent, AgentRuntime, EventType, RunContext
from app.agents.definitions import AGENT_SPECS, ORCHESTRATOR_INSTRUCTION, specs_for
from app.agents.tools.adapters import langchain_tools
from app.agents.tools.core import tool_document_ids, tool_user_id
from app.config import AgentFramework, settings
from app.core.errors import FrameworkNotAvailableError
from app.core.logging import get_logger
from app.llm.registry import ModelSpec, build_chat_model

log = get_logger(__name__)

MAX_TOOL_PASSES = 3
HISTORY_TURNS = 12
HISTORY_CHAR_BUDGET = 12_000
PER_MESSAGE_CHAR_CAP = 2_000

CONTEXT_KEYS = (
    ("research_findings", "Research findings"),
    ("retrieved_context", "Retrieved passages"),
    ("analysis", "Analysis"),
    ("compliance_review", "Compliance review"),
    ("final_answer", "Current draft"),
)


class MeshState(TypedDict, total=False):
    messages: Annotated[list[Any], operator.add]
    task: str
    history: str
    plan: list[str]
    route: str
    research_findings: str
    retrieved_context: str
    analysis: str
    compliance_review: str
    final_answer: str
    citations: Annotated[list[dict[str, Any]], operator.add]
    steps: Annotated[list[dict[str, Any]], operator.add]
    usage: Annotated[list[dict[str, int]], operator.add]
    iterations: int


class LangGraphRuntime(AgentRuntime):
    framework = AgentFramework.LANGGRAPH
    display_name = "LangGraph Supervisor"
    description = "Explicit StateGraph with a structured-output supervisor and parallel specialist fan-out."

    def _spec(self, ctx: RunContext) -> ModelSpec:
        return ModelSpec(
            provider=ctx.provider, model=ctx.model, temperature=ctx.temperature, max_tokens=ctx.max_tokens
        )

    def _build_graph(self, ctx: RunContext) -> Any:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:  # pragma: no cover
            raise FrameworkNotAvailableError("langgraph is not installed. `pip install langgraph`") from exc

        llm = build_chat_model(self._spec(ctx))
        enabled = {s.name for s in specs_for(ctx.enabled_agents)}
        if not enabled:
            raise FrameworkNotAvailableError("No specialists are enabled for this run.")

        memory_block = ctx.memory_block()

        # Tools are stable for the life of the graph; building them per node
        # invocation re-instantiates the whole surface on every hop.
        tool_cache: dict[str, list[Any]] = {}

        def tools_for(name: str) -> list[Any]:
            if name not in tool_cache:
                tool_cache[name] = langchain_tools(AGENT_SPECS[name].tools)
            return tool_cache[name]

        async def _run_specialist(name: str, state: MeshState) -> dict[str, Any]:
            spec = AGENT_SPECS[name]
            tools = tools_for(name)
            model = llm.bind_tools(tools) if tools else llm

            context_bits = []
            if state.get("history"):
                context_bits.append(f"Conversation so far:\n{state['history']}")
            context_bits.append(f"User request:\n{state['task']}")
            for key, header in CONTEXT_KEYS:
                if state.get(key) and key != spec.output_key:
                    context_bits.append(f"{header}:\n{state[key]}")

            system = spec.instruction + (f"\n\n{memory_block}" if memory_block else "")
            messages: list[Any] = [
                {"role": "system", "content": system},
                {"role": "user", "content": "\n\n".join(context_bits)},
            ]

            collected_steps: list[dict[str, Any]] = []
            citations: list[dict[str, Any]] = []
            usage: list[dict[str, int]] = []
            tool_map = {t.name: t for t in tools}

            # Bounded tool loop. Three passes is enough for every specialist we
            # have; a runaway loop here is how agent systems burn a budget.
            for pass_no in range(MAX_TOOL_PASSES):
                response = await model.ainvoke(messages)
                messages.append(response)
                _collect_usage(usage, response)

                calls = getattr(response, "tool_calls", None) or []
                if not calls:
                    break

                for call in calls:
                    call_id = call.get("id")
                    tool = tool_map.get(call["name"])
                    started = time.perf_counter()

                    if tool is None:
                        # Every tool_call id must get a reply. Dropping one leaves
                        # a dangling id and the next provider call 400s.
                        result: Any = (
                            f"Error: no tool named {call['name']}. "
                            f"Available: {', '.join(sorted(tool_map)) or 'none'}."
                        )
                        log.warning("langgraph_unknown_tool", agent=name, tool=call["name"])
                    else:
                        try:
                            result = await tool.ainvoke(call["args"])
                        except Exception as exc:
                            # Feed the failure back so the specialist can recover
                            # instead of killing the whole run.
                            log.warning("langgraph_tool_failed", agent=name, tool=call["name"],
                                        error=str(exc)[:200])
                            result = f"Error: {type(exc).__name__}: {exc}"[:800]

                    collected_steps.append(
                        {
                            "agent": name,
                            "type": "tool",
                            "tool": call["name"],
                            "input": call["args"],
                            "output": str(result)[:2000],
                            "duration_ms": int((time.perf_counter() - started) * 1000),
                        }
                    )
                    citations.extend(_extract_citations(result))
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": str(result)})

                if pass_no == MAX_TOOL_PASSES - 1:
                    # Budget exhausted mid-tool-loop. Without this the last
                    # message is a tool result and the specialist's "output"
                    # ends up being raw tool JSON.
                    final = await llm.ainvoke(
                        messages + [{"role": "user",
                                     "content": "Tool budget reached. Answer now from what you have."}]
                    )
                    messages.append(final)
                    _collect_usage(usage, final)

            text = _last_ai_text(messages)
            return {
                spec.output_key: text,
                "steps": collected_steps + [{"agent": name, "type": "agent", "output": text[:2000]}],
                "citations": citations,
                "usage": usage,
            }

        # The router may only choose stages that actually exist this run.
        route_options = tuple(
            ["research_phase"] if enabled & {"researcher", "retriever"} else []
        ) + tuple(n for n in ("analyst", "compliance", "writer") if n in enabled) + ("finish",)

        async def supervisor(state: MeshState) -> dict[str, Any]:
            """Routes. Emits a plan on the first pass, a next-hop afterwards."""
            from pydantic import BaseModel, Field

            class Route(BaseModel):
                next: Literal[route_options] = Field(  # type: ignore[valid-type]
                    description="Which stage runs next."
                )
                plan: list[str] = Field(default_factory=list, description="Ordered plan, first call only.")
                reason: str = Field(default="", description="One sentence of justification.")

            state_view = {key: bool(state.get(key)) for key, _ in CONTEXT_KEYS}
            prompt = (
                f"{ORCHESTRATOR_INSTRUCTION}\n\n"
                + (f"{memory_block}\n\n" if memory_block else "")
                + (f"Conversation so far:\n{state['history']}\n\n" if state.get("history") else "")
                + f"Enabled specialists: {sorted(enabled)}\n"
                f"User request: {state['task']}\n"
                f"Completed so far: {json.dumps(state_view)}\n"
                f"Iterations used: {state.get('iterations', 0)} of {settings.agent.max_orchestrator_steps}\n\n"
                "Choose the next stage. 'research_phase' runs researcher and retriever in parallel. "
                "Choose 'finish' only if the request needs no specialist work at all."
            )

            try:
                router = llm.with_structured_output(Route)
                decision: Any = await router.ainvoke(prompt)
                next_route, plan, reason = decision.next, decision.plan, decision.reason
            except Exception as exc:
                # Not every provider supports structured output, and schema
                # coercion can fail on a bad generation. Falling through to a
                # deterministic route beats killing the run.
                log.warning("langgraph_router_fallback", error=str(exc)[:200])
                next_route, plan, reason = _fallback_route(state, enabled), [], "router fallback"

            return {
                "route": next_route,
                "plan": plan or state.get("plan", []),
                "iterations": state.get("iterations", 0) + 1,
                "steps": [{"agent": "orchestrator", "type": "route", "output": next_route, "reason": reason}],
            }

        async def researcher(state: MeshState) -> dict[str, Any]:
            return await _run_specialist("researcher", state)

        async def retriever(state: MeshState) -> dict[str, Any]:
            return await _run_specialist("retriever", state)

        async def analyst(state: MeshState) -> dict[str, Any]:
            return await _run_specialist("analyst", state)

        async def compliance(state: MeshState) -> dict[str, Any]:
            return await _run_specialist("compliance", state)

        async def writer(state: MeshState) -> dict[str, Any]:
            return await _run_specialist("writer", state)

        async def fan_in(state: MeshState) -> dict[str, Any]:
            return {}

        def route_from_supervisor(state: MeshState) -> Sequence[str] | str:
            if state.get("iterations", 0) > settings.agent.max_orchestrator_steps:
                return "writer" if "writer" in enabled else "__end__"
            route = state.get("route", "finish")
            if route == "research_phase":
                parallel = [n for n in ("researcher", "retriever") if n in enabled]
                if parallel:
                    return parallel
                return "writer" if "writer" in enabled else "__end__"
            if route == "finish":
                return "writer" if "writer" in enabled else "__end__"
            # Never route to a node whose specialist is disabled - it would run
            # anyway, because the node exists in the graph regardless.
            if route in enabled:
                return route
            return "writer" if "writer" in enabled else "__end__"

        graph = StateGraph(MeshState)
        graph.add_node("supervisor", supervisor)
        graph.add_node("researcher", researcher)
        graph.add_node("retriever", retriever)
        graph.add_node("fan_in", fan_in)
        graph.add_node("analyst", analyst)
        graph.add_node("compliance", compliance)
        graph.add_node("writer", writer)

        graph.add_edge(START, "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            route_from_supervisor,
            {
                "researcher": "researcher",
                "retriever": "retriever",
                "analyst": "analyst",
                "compliance": "compliance",
                "writer": "writer",
                "__end__": END,
            },
        )
        # Parallel branches rejoin at fan_in, then go back to the supervisor for
        # the next decision. This is the loop that makes the graph adaptive.
        graph.add_edge("researcher", "fan_in")
        graph.add_edge("retriever", "fan_in")
        graph.add_edge("fan_in", "supervisor")
        graph.add_edge("analyst", "supervisor")
        graph.add_edge("compliance", "supervisor")
        graph.add_edge("writer", END)

        return graph.compile()

    async def stream(self, ctx: RunContext) -> AsyncIterator[AgentEvent]:
        tool_user_id.set(ctx.user_id)
        tool_document_ids.set(tuple(ctx.document_ids))
        run_id = str(ctx.run_id)

        yield AgentEvent(EventType.RUN_STARTED, {"framework": self.framework.value}, agent="orchestrator",
                         run_id=run_id)
        try:
            app = self._build_graph(ctx)
            initial: MeshState = {
                "task": ctx.message,
                "history": _render_history(ctx),
                "messages": [],
                "iterations": 0,
            }

            # The supervisor loop means every specialist costs two graph steps.
            # LangGraph's default of 25 is not enough for a full pipeline.
            config: dict[str, Any] = {
                "recursion_limit": getattr(settings.agent, "max_graph_steps", 60),
                "configurable": {"thread_id": run_id, "user_id": ctx.user_id},
            }

            final_state: dict[str, Any] = {}
            citations: list[dict[str, Any]] = []
            seen_citations: set[tuple[Any, Any, Any]] = set()
            usage = {"input_tokens": 0, "output_tokens": 0}
            seen_agents: set[str] = set()
            streamed_answer = ""

            timeout = getattr(settings.agent, "run_timeout_seconds", None)
            stream = app.astream(initial, config=config, stream_mode=["updates", "messages"])

            async for mode, chunk in _with_timeout(stream, timeout):
                if mode == "messages":
                    # Real token streaming for the composing agent. The old code
                    # sliced the finished answer after the fact, so the UI sat
                    # blank for the whole run.
                    message, meta = chunk if isinstance(chunk, tuple) else (chunk, {})
                    if (meta or {}).get("langgraph_node") != "writer":
                        continue
                    if getattr(message, "type", "") not in ("ai", "AIMessageChunk"):
                        continue
                    token = _text_of(message)
                    if token:
                        streamed_answer += token
                        yield AgentEvent(EventType.TOKEN, {"text": token}, agent="writer", run_id=run_id)
                    continue

                for node, update in (chunk or {}).items():
                    if node == "fan_in":
                        continue
                    update = update or {}

                    for entry in update.get("usage", []) or []:
                        usage["input_tokens"] += int(entry.get("input_tokens", 0) or 0)
                        usage["output_tokens"] += int(entry.get("output_tokens", 0) or 0)

                    if node == "supervisor":
                        plan = update.get("plan")
                        if plan:
                            yield AgentEvent(EventType.PLAN, {"plan": plan}, agent="orchestrator", run_id=run_id)
                        yield AgentEvent(
                            EventType.HANDOFF, {"to": update.get("route")}, agent="orchestrator", run_id=run_id
                        )
                        final_state["route"] = update.get("route")
                        final_state["plan"] = plan or final_state.get("plan")
                        continue

                    if node not in seen_agents:
                        seen_agents.add(node)
                        yield AgentEvent(EventType.AGENT_STARTED, {}, agent=node, run_id=run_id)

                    for step in update.get("steps", []) or []:
                        if step.get("type") == "tool":
                            yield AgentEvent(
                                EventType.TOOL_CALL,
                                {"tool": step["tool"], "input": step["input"]},
                                agent=node, run_id=run_id,
                            )
                            yield AgentEvent(
                                EventType.TOOL_RESULT,
                                {"tool": step["tool"], "output": step["output"][:800],
                                 "duration_ms": step.get("duration_ms")},
                                agent=node, run_id=run_id,
                            )

                    # Accumulate across nodes. final_state.update() would drop
                    # every earlier node's citations on the floor.
                    fresh = []
                    for cite in update.get("citations", []) or []:
                        key = (cite.get("filename"), cite.get("page"), cite.get("marker"))
                        if key not in seen_citations:
                            seen_citations.add(key)
                            citations.append(cite)
                            fresh.append(cite)
                    if fresh:
                        yield AgentEvent(EventType.CITATION, {"citations": fresh}, agent=node, run_id=run_id)

                    spec = AGENT_SPECS.get(node)
                    output = update.get(spec.output_key) if spec else None
                    if spec and output is not None:
                        final_state[spec.output_key] = output
                    yield AgentEvent(EventType.AGENT_FINISHED, {"summary": (output or "")[:500]}, agent=node,
                                     run_id=run_id)

            answer = final_state.get("final_answer") or streamed_answer

            if not answer:
                # Analysis or raw passages are working material, not an answer.
                # Say so rather than shipping retrieval output as the response.
                partial = final_state.get("analysis") or final_state.get("research_findings")
                yield AgentEvent(
                    EventType.ERROR,
                    {"message": "The graph finished without composing an answer.", "code": "no_output",
                     "partial": (partial or "")[:1000]},
                    agent="orchestrator", run_id=run_id,
                )
                return

            if not streamed_answer:
                # Non-streaming provider: send the composed answer in slices so
                # the client still gets token events.
                for piece in _slice(answer):
                    yield AgentEvent(EventType.TOKEN, {"text": piece}, agent="writer", run_id=run_id)

            if usage["input_tokens"] or usage["output_tokens"]:
                yield AgentEvent(EventType.USAGE, usage, agent="orchestrator", run_id=run_id)

            yield AgentEvent(
                EventType.RUN_FINISHED,
                {"text": answer, "citations": citations, "plan": final_state.get("plan", [])},
                agent="orchestrator", run_id=run_id,
            )

        except asyncio.CancelledError:
            raise
        except FrameworkNotAvailableError as exc:
            yield AgentEvent(EventType.ERROR, {"message": exc.message, "code": exc.code}, run_id=run_id)
        except asyncio.TimeoutError:
            yield AgentEvent(
                EventType.ERROR,
                {"message": "The graph exceeded its time budget.", "code": "run_timeout"},
                agent="orchestrator", run_id=run_id,
            )
        except Exception as exc:
            log.exception("langgraph_run_failed")
            if type(exc).__name__ == "GraphRecursionError":
                yield AgentEvent(
                    EventType.ERROR,
                    {"message": ("The supervisor loop hit its step limit. Raise "
                                 "settings.agent.max_graph_steps or narrow the request."),
                     "code": "recursion_limit"},
                    agent="orchestrator", run_id=run_id,
                )
                return
            yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]},
                             agent="orchestrator", run_id=run_id)


async def _with_timeout(stream: AsyncIterator[Any], seconds: float | None) -> AsyncIterator[Any]:
    """Per-chunk timeout, so a stalled provider does not hang the run forever
    while a long legitimate graph is left alone."""
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


def _render_history(ctx: RunContext) -> str:
    """The old code loaded history into state['messages'] and then never read it -
    specialists only ever saw the current task, so multi-turn context was lost."""
    if not ctx.history:
        return ""
    lines: list[str] = []
    used = 0
    for m in reversed(ctx.history[-HISTORY_TURNS:]):
        content = str(m.get("content", ""))
        if len(content) > PER_MESSAGE_CHAR_CAP:
            content = content[:PER_MESSAGE_CHAR_CAP] + " …[truncated]"
        line = f"{m.get('role', 'user')}: {content}"
        if used + len(line) > HISTORY_CHAR_BUDGET:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(reversed(lines))


def _fallback_route(state: MeshState, enabled: set[str]) -> str:
    """Deterministic next hop when structured routing is unavailable."""
    if not (state.get("research_findings") or state.get("retrieved_context")):
        if enabled & {"researcher", "retriever"}:
            return "research_phase"
    if "analyst" in enabled and not state.get("analysis"):
        return "analyst"
    if "compliance" in enabled and state.get("final_answer") and not state.get("compliance_review"):
        return "compliance"
    return "writer" if "writer" in enabled else "finish"


def _collect_usage(sink: list[dict[str, int]], message: Any) -> None:
    meta = getattr(message, "usage_metadata", None)
    if not isinstance(meta, dict):
        return
    sink.append(
        {
            "input_tokens": int(meta.get("input_tokens", 0) or 0),
            "output_tokens": int(meta.get("output_tokens", 0) or 0),
        }
    )


def _last_ai_text(messages: list[Any]) -> str:
    """Walk back to the last assistant message that actually has text. Taking
    messages[-1] blindly returns raw tool JSON whenever the loop ends on a tool
    result."""
    for message in reversed(messages):
        if isinstance(message, dict):
            if message.get("role") in ("tool", "user", "system"):
                continue
            text = str(message.get("content", ""))
        else:
            if getattr(message, "type", "") not in ("ai", "AIMessageChunk", ""):
                continue
            text = _text_of(message)
        if text.strip():
            return text
    return ""


def _text_of(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type", "text") == "text"
        )
    if isinstance(content, dict):
        return str(content.get("content", ""))
    return str(content)


def _extract_citations(tool_output: Any) -> list[dict[str, Any]]:
    payload: Any = tool_output
    if isinstance(tool_output, str):
        try:
            payload = json.loads(tool_output)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []
    if not isinstance(payload, dict):
        return []
    return [
        {"filename": p.get("filename"), "page": p.get("page"), "marker": p.get("citation")}
        for p in (payload.get("passages") or [])
        if isinstance(p, dict)
    ]


def _slice(text: str, size: int = 24) -> list[str]:
    words = text.split(" ")
    if not words:
        return []
    return [" ".join(words[i:i + size]) + (" " if i + size < len(words) else "") for i in range(0, len(words), size)]
# """LangGraph adapter - explicit supervisor graph over the five specialists.

# Topology:

#     entry -> supervisor -> {researcher, retriever} (parallel fan-out)
#                         -> analyst      (conditional: numbers present)
#                         -> compliance   (conditional: draft exists)
#                         -> writer -> END

# The supervisor is a real node with a structured-output router, not a prompt that
# "decides" in free text. Structured routing is the difference between a graph you
# can test and one you can only observe.
# """
# from __future__ import annotations

# import json
# import operator
# import time
# from collections.abc import AsyncIterator, Sequence
# from typing import Annotated, Any, Literal, TypedDict

# from app.agents.base import AgentEvent, AgentRuntime, EventType, RunContext
# from app.agents.definitions import AGENT_SPECS, ORCHESTRATOR_INSTRUCTION, specs_for
# from app.agents.tools.adapters import langchain_tools
# from app.agents.tools.core import tool_document_ids, tool_user_id
# from app.config import AgentFramework, settings
# from app.core.logging import get_logger
# from app.llm.registry import ModelSpec, build_chat_model

# log = get_logger(__name__)


# class MeshState(TypedDict, total=False):
#     messages: Annotated[list[Any], operator.add]
#     task: str
#     plan: list[str]
#     route: str
#     research_findings: str
#     retrieved_context: str
#     analysis: str
#     compliance_review: str
#     final_answer: str
#     citations: Annotated[list[dict[str, Any]], operator.add]
#     steps: Annotated[list[dict[str, Any]], operator.add]
#     iterations: int


# class LangGraphRuntime(AgentRuntime):
#     framework = AgentFramework.LANGGRAPH
#     display_name = "LangGraph Supervisor"
#     description = "Explicit StateGraph with a structured-output supervisor and parallel specialist fan-out."

#     def _spec(self, ctx: RunContext) -> ModelSpec:
#         return ModelSpec(
#             provider=ctx.provider, model=ctx.model, temperature=ctx.temperature, max_tokens=ctx.max_tokens
#         )

#     def _build_graph(self, ctx: RunContext) -> Any:
#         from langgraph.graph import END, START, StateGraph

#         llm = build_chat_model(self._spec(ctx))
#         enabled = {s.name for s in specs_for(ctx.enabled_agents)}
#         memory_block = ctx.memory_block()

#         async def _run_specialist(name: str, state: MeshState) -> dict[str, Any]:
#             spec = AGENT_SPECS[name]
#             tools = langchain_tools(spec.tools)
#             model = llm.bind_tools(tools) if tools else llm

#             context_bits = [f"User request:\n{state['task']}"]
#             for key, header in (
#                 ("research_findings", "Research findings"),
#                 ("retrieved_context", "Retrieved passages"),
#                 ("analysis", "Analysis"),
#                 ("compliance_review", "Compliance review"),
#                 ("final_answer", "Current draft"),
#             ):
#                 if state.get(key) and key != spec.output_key:
#                     context_bits.append(f"{header}:\n{state[key]}")

#             system = spec.instruction + (f"\n\n{memory_block}" if memory_block else "")
#             messages: list[Any] = [
#                 {"role": "system", "content": system},
#                 {"role": "user", "content": "\n\n".join(context_bits)},
#             ]

#             collected_steps: list[dict[str, Any]] = []
#             citations: list[dict[str, Any]] = []

#             # Bounded tool loop. Three passes is enough for every specialist we
#             # have; a runaway loop here is how agent systems burn a budget.
#             for _ in range(3):
#                 response = await model.ainvoke(messages)
#                 messages.append(response)
#                 calls = getattr(response, "tool_calls", None) or []
#                 if not calls:
#                     break
#                 tool_map = {t.name: t for t in tools}
#                 for call in calls:
#                     tool = tool_map.get(call["name"])
#                     if tool is None:
#                         continue
#                     started = time.perf_counter()
#                     result = await tool.ainvoke(call["args"])
#                     collected_steps.append(
#                         {
#                             "agent": name,
#                             "type": "tool",
#                             "tool": call["name"],
#                             "input": call["args"],
#                             "output": str(result)[:2000],
#                             "duration_ms": int((time.perf_counter() - started) * 1000),
#                         }
#                     )
#                     citations.extend(_extract_citations(result))
#                     messages.append({"role": "tool", "tool_call_id": call["id"], "content": str(result)})

#             text = _text_of(messages[-1])
#             return {
#                 spec.output_key: text,
#                 "steps": collected_steps + [{"agent": name, "type": "agent", "output": text[:2000]}],
#                 "citations": citations,
#             }

#         async def supervisor(state: MeshState) -> dict[str, Any]:
#             """Routes. Emits a plan on the first pass, a next-hop afterwards."""
#             from pydantic import BaseModel, Field

#             class Route(BaseModel):
#                 next: Literal["research_phase", "analyst", "compliance", "writer", "finish"] = Field(
#                     description="Which stage runs next."
#                 )
#                 plan: list[str] = Field(default_factory=list, description="Ordered plan, first call only.")
#                 reason: str = Field(default="", description="One sentence of justification.")

#             router = llm.with_structured_output(Route)
#             state_view = {
#                 key: bool(state.get(key))
#                 for key in ("research_findings", "retrieved_context", "analysis", "compliance_review", "final_answer")
#             }
#             prompt = (
#                 f"{ORCHESTRATOR_INSTRUCTION}\n\n"
#                 f"Enabled specialists: {sorted(enabled)}\n"
#                 f"User request: {state['task']}\n"
#                 f"Completed so far: {json.dumps(state_view)}\n"
#                 f"Iterations used: {state.get('iterations', 0)} of {settings.agent.max_orchestrator_steps}\n\n"
#                 "Choose the next stage. 'research_phase' runs researcher and retriever in parallel. "
#                 "Choose 'finish' only if the request needs no specialist work at all."
#             )
#             decision: Any = await router.ainvoke(prompt)
#             return {
#                 "route": decision.next,
#                 "plan": decision.plan or state.get("plan", []),
#                 "iterations": state.get("iterations", 0) + 1,
#                 "steps": [{"agent": "orchestrator", "type": "route", "output": decision.next,
#                            "reason": decision.reason}],
#             }

#         async def researcher(state: MeshState) -> dict[str, Any]:
#             return await _run_specialist("researcher", state)

#         async def retriever(state: MeshState) -> dict[str, Any]:
#             return await _run_specialist("retriever", state)

#         async def analyst(state: MeshState) -> dict[str, Any]:
#             return await _run_specialist("analyst", state)

#         async def compliance(state: MeshState) -> dict[str, Any]:
#             return await _run_specialist("compliance", state)

#         async def writer(state: MeshState) -> dict[str, Any]:
#             return await _run_specialist("writer", state)

#         async def fan_in(state: MeshState) -> dict[str, Any]:
#             return {}

#         def route_from_supervisor(state: MeshState) -> Sequence[str] | str:
#             if state.get("iterations", 0) > settings.agent.max_orchestrator_steps:
#                 return "writer"
#             route = state.get("route", "finish")
#             if route == "research_phase":
#                 parallel = [n for n in ("researcher", "retriever") if n in enabled]
#                 return parallel or ["writer"]
#             if route == "finish":
#                 return "writer" if "writer" in enabled else "__end__"
#             return route if route in enabled else "writer"

#         graph = StateGraph(MeshState)
#         graph.add_node("supervisor", supervisor)
#         graph.add_node("researcher", researcher)
#         graph.add_node("retriever", retriever)
#         graph.add_node("fan_in", fan_in)
#         graph.add_node("analyst", analyst)
#         graph.add_node("compliance", compliance)
#         graph.add_node("writer", writer)

#         graph.add_edge(START, "supervisor")
#         graph.add_conditional_edges(
#             "supervisor",
#             route_from_supervisor,
#             {
#                 "researcher": "researcher",
#                 "retriever": "retriever",
#                 "analyst": "analyst",
#                 "compliance": "compliance",
#                 "writer": "writer",
#                 "__end__": END,
#             },
#         )
#         # Parallel branches rejoin at fan_in, then go back to the supervisor for
#         # the next decision. This is the loop that makes the graph adaptive.
#         graph.add_edge("researcher", "fan_in")
#         graph.add_edge("retriever", "fan_in")
#         graph.add_edge("fan_in", "supervisor")
#         graph.add_edge("analyst", "supervisor")
#         graph.add_edge("compliance", "supervisor")
#         graph.add_edge("writer", END)

#         return graph.compile()

#     async def stream(self, ctx: RunContext) -> AsyncIterator[AgentEvent]:
#         tool_user_id.set(ctx.user_id)
#         tool_document_ids.set(tuple(ctx.document_ids))
#         run_id = str(ctx.run_id)

#         yield AgentEvent(EventType.RUN_STARTED, {"framework": self.framework.value}, agent="orchestrator",
#                          run_id=run_id)
#         try:
#             app = self._build_graph(ctx)
#             initial: MeshState = {
#                 "task": ctx.message,
#                 "messages": [{"role": m["role"], "content": m["content"]} for m in ctx.history],
#                 "iterations": 0,
#             }
#             final_state: dict[str, Any] = {}
#             seen_agents: set[str] = set()

#             async for chunk in app.astream(initial, stream_mode="updates"):
#                 for node, update in chunk.items():
#                     if node in ("fan_in",):
#                         continue
#                     if node == "supervisor":
#                         plan = update.get("plan")
#                         if plan:
#                             yield AgentEvent(EventType.PLAN, {"plan": plan}, agent="orchestrator", run_id=run_id)
#                         yield AgentEvent(
#                             EventType.HANDOFF, {"to": update.get("route")}, agent="orchestrator", run_id=run_id
#                         )
#                         continue

#                     if node not in seen_agents:
#                         seen_agents.add(node)
#                         yield AgentEvent(EventType.AGENT_STARTED, {}, agent=node, run_id=run_id)

#                     for step in update.get("steps", []):
#                         if step.get("type") == "tool":
#                             yield AgentEvent(
#                                 EventType.TOOL_CALL,
#                                 {"tool": step["tool"], "input": step["input"]},
#                                 agent=node, run_id=run_id,
#                             )
#                             yield AgentEvent(
#                                 EventType.TOOL_RESULT,
#                                 {"tool": step["tool"], "output": step["output"][:800],
#                                  "duration_ms": step.get("duration_ms")},
#                                 agent=node, run_id=run_id,
#                             )
#                     if update.get("citations"):
#                         yield AgentEvent(EventType.CITATION, {"citations": update["citations"]}, agent=node,
#                                          run_id=run_id)

#                     spec = AGENT_SPECS.get(node)
#                     output = update.get(spec.output_key) if spec else None
#                     yield AgentEvent(EventType.AGENT_FINISHED, {"summary": (output or "")[:500]}, agent=node,
#                                      run_id=run_id)
#                     final_state.update(update)

#             answer = final_state.get("final_answer") or final_state.get("analysis") or \
#                 final_state.get("retrieved_context") or "I could not produce an answer for that request."

#             # Stream the composed answer back in readable slices.
#             for piece in _slice(answer):
#                 yield AgentEvent(EventType.TOKEN, {"text": piece}, agent="writer", run_id=run_id)

#             yield AgentEvent(
#                 EventType.RUN_FINISHED,
#                 {"text": answer, "citations": final_state.get("citations", [])},
#                 agent="orchestrator", run_id=run_id,
#             )
#         except Exception as exc:
#             log.exception("langgraph_run_failed")
#             yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]},
#                              agent="orchestrator", run_id=run_id)


# def _text_of(message: Any) -> str:
#     content = getattr(message, "content", message)
#     if isinstance(content, str):
#         return content
#     if isinstance(content, list):
#         return "".join(part.get("text", "") for part in content if isinstance(part, dict))
#     if isinstance(content, dict):
#         return str(content.get("content", ""))
#     return str(content)


# def _extract_citations(tool_output: Any) -> list[dict[str, Any]]:
#     try:
#         payload = json.loads(tool_output if isinstance(tool_output, str) else json.dumps(tool_output))
#     except (json.JSONDecodeError, TypeError):
#         return []
#     return [
#         {"filename": p.get("filename"), "page": p.get("page"), "marker": p.get("citation")}
#         for p in payload.get("passages", [])
#         if isinstance(p, dict)
#     ]


# def _slice(text: str, size: int = 24) -> list[str]:
#     words = text.split(" ")
#     return [" ".join(words[i:i + size]) + (" " if i + size < len(words) else "") for i in range(0, len(words), size)]
