"""LangGraph adapter - explicit supervisor graph over the five specialists.

Topology:

    entry -> supervisor -> {researcher, retriever} (parallel fan-out)
                        -> analyst      (conditional: numbers present)
                        -> compliance   (conditional: draft exists)
                        -> writer -> END

The supervisor is a real node with a structured-output router, not a prompt that
"decides" in free text. Structured routing is the difference between a graph you
can test and one you can only observe.
"""
from __future__ import annotations

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
from app.core.logging import get_logger
from app.llm.registry import ModelSpec, build_chat_model

log = get_logger(__name__)


class MeshState(TypedDict, total=False):
    messages: Annotated[list[Any], operator.add]
    task: str
    plan: list[str]
    route: str
    research_findings: str
    retrieved_context: str
    analysis: str
    compliance_review: str
    final_answer: str
    citations: Annotated[list[dict[str, Any]], operator.add]
    steps: Annotated[list[dict[str, Any]], operator.add]
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
        from langgraph.graph import END, START, StateGraph

        llm = build_chat_model(self._spec(ctx))
        enabled = {s.name for s in specs_for(ctx.enabled_agents)}
        memory_block = ctx.memory_block()

        async def _run_specialist(name: str, state: MeshState) -> dict[str, Any]:
            spec = AGENT_SPECS[name]
            tools = langchain_tools(spec.tools)
            model = llm.bind_tools(tools) if tools else llm

            context_bits = [f"User request:\n{state['task']}"]
            for key, header in (
                ("research_findings", "Research findings"),
                ("retrieved_context", "Retrieved passages"),
                ("analysis", "Analysis"),
                ("compliance_review", "Compliance review"),
                ("final_answer", "Current draft"),
            ):
                if state.get(key) and key != spec.output_key:
                    context_bits.append(f"{header}:\n{state[key]}")

            system = spec.instruction + (f"\n\n{memory_block}" if memory_block else "")
            messages: list[Any] = [
                {"role": "system", "content": system},
                {"role": "user", "content": "\n\n".join(context_bits)},
            ]

            collected_steps: list[dict[str, Any]] = []
            citations: list[dict[str, Any]] = []

            # Bounded tool loop. Three passes is enough for every specialist we
            # have; a runaway loop here is how agent systems burn a budget.
            for _ in range(3):
                response = await model.ainvoke(messages)
                messages.append(response)
                calls = getattr(response, "tool_calls", None) or []
                if not calls:
                    break
                tool_map = {t.name: t for t in tools}
                for call in calls:
                    tool = tool_map.get(call["name"])
                    if tool is None:
                        continue
                    started = time.perf_counter()
                    result = await tool.ainvoke(call["args"])
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
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": str(result)})

            text = _text_of(messages[-1])
            return {
                spec.output_key: text,
                "steps": collected_steps + [{"agent": name, "type": "agent", "output": text[:2000]}],
                "citations": citations,
            }

        async def supervisor(state: MeshState) -> dict[str, Any]:
            """Routes. Emits a plan on the first pass, a next-hop afterwards."""
            from pydantic import BaseModel, Field

            class Route(BaseModel):
                next: Literal["research_phase", "analyst", "compliance", "writer", "finish"] = Field(
                    description="Which stage runs next."
                )
                plan: list[str] = Field(default_factory=list, description="Ordered plan, first call only.")
                reason: str = Field(default="", description="One sentence of justification.")

            router = llm.with_structured_output(Route)
            state_view = {
                key: bool(state.get(key))
                for key in ("research_findings", "retrieved_context", "analysis", "compliance_review", "final_answer")
            }
            prompt = (
                f"{ORCHESTRATOR_INSTRUCTION}\n\n"
                f"Enabled specialists: {sorted(enabled)}\n"
                f"User request: {state['task']}\n"
                f"Completed so far: {json.dumps(state_view)}\n"
                f"Iterations used: {state.get('iterations', 0)} of {settings.agent.max_orchestrator_steps}\n\n"
                "Choose the next stage. 'research_phase' runs researcher and retriever in parallel. "
                "Choose 'finish' only if the request needs no specialist work at all."
            )
            decision: Any = await router.ainvoke(prompt)
            return {
                "route": decision.next,
                "plan": decision.plan or state.get("plan", []),
                "iterations": state.get("iterations", 0) + 1,
                "steps": [{"agent": "orchestrator", "type": "route", "output": decision.next,
                           "reason": decision.reason}],
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
                return "writer"
            route = state.get("route", "finish")
            if route == "research_phase":
                parallel = [n for n in ("researcher", "retriever") if n in enabled]
                return parallel or ["writer"]
            if route == "finish":
                return "writer" if "writer" in enabled else "__end__"
            return route if route in enabled else "writer"

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
                "messages": [{"role": m["role"], "content": m["content"]} for m in ctx.history],
                "iterations": 0,
            }
            final_state: dict[str, Any] = {}
            seen_agents: set[str] = set()

            async for chunk in app.astream(initial, stream_mode="updates"):
                for node, update in chunk.items():
                    if node in ("fan_in",):
                        continue
                    if node == "supervisor":
                        plan = update.get("plan")
                        if plan:
                            yield AgentEvent(EventType.PLAN, {"plan": plan}, agent="orchestrator", run_id=run_id)
                        yield AgentEvent(
                            EventType.HANDOFF, {"to": update.get("route")}, agent="orchestrator", run_id=run_id
                        )
                        continue

                    if node not in seen_agents:
                        seen_agents.add(node)
                        yield AgentEvent(EventType.AGENT_STARTED, {}, agent=node, run_id=run_id)

                    for step in update.get("steps", []):
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
                    if update.get("citations"):
                        yield AgentEvent(EventType.CITATION, {"citations": update["citations"]}, agent=node,
                                         run_id=run_id)

                    spec = AGENT_SPECS.get(node)
                    output = update.get(spec.output_key) if spec else None
                    yield AgentEvent(EventType.AGENT_FINISHED, {"summary": (output or "")[:500]}, agent=node,
                                     run_id=run_id)
                    final_state.update(update)

            answer = final_state.get("final_answer") or final_state.get("analysis") or \
                final_state.get("retrieved_context") or "I could not produce an answer for that request."

            # Stream the composed answer back in readable slices.
            for piece in _slice(answer):
                yield AgentEvent(EventType.TOKEN, {"text": piece}, agent="writer", run_id=run_id)

            yield AgentEvent(
                EventType.RUN_FINISHED,
                {"text": answer, "citations": final_state.get("citations", [])},
                agent="orchestrator", run_id=run_id,
            )
        except Exception as exc:
            log.exception("langgraph_run_failed")
            yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]},
                             agent="orchestrator", run_id=run_id)


def _text_of(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if isinstance(content, dict):
        return str(content.get("content", ""))
    return str(content)


def _extract_citations(tool_output: Any) -> list[dict[str, Any]]:
    try:
        payload = json.loads(tool_output if isinstance(tool_output, str) else json.dumps(tool_output))
    except (json.JSONDecodeError, TypeError):
        return []
    return [
        {"filename": p.get("filename"), "page": p.get("page"), "marker": p.get("citation")}
        for p in payload.get("passages", [])
        if isinstance(p, dict)
    ]


def _slice(text: str, size: int = 24) -> list[str]:
    words = text.split(" ")
    return [" ".join(words[i:i + size]) + (" " if i + size < len(words) else "") for i in range(0, len(words), size)]
