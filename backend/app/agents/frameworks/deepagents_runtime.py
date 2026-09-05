"""LangChain DeepAgents adapter.

DeepAgents is the opposite philosophy to the ADK pipeline: instead of declaring
the workflow, you give one capable agent a planning tool, a virtual filesystem
and a roster of subagents, and let it decide. It is the right choice for
open-ended research where the shape of the work is not known in advance.

Our five specialists map onto declarative subagent specs. The main agent gets
the orchestrator instruction and the `task` tool that spawns them.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import AgentEvent, AgentRuntime, EventType, RunContext
from app.agents.definitions import ORCHESTRATOR_INSTRUCTION, specs_for
from app.agents.tools.adapters import langchain_tools
from app.agents.tools.core import tool_document_ids, tool_user_id
from app.config import AgentFramework
from app.core.errors import FrameworkNotAvailableError
from app.core.logging import get_logger
from app.llm.registry import ModelSpec, build_chat_model

log = get_logger(__name__)


class DeepAgentsRuntime(AgentRuntime):
    framework = AgentFramework.DEEPAGENTS
    display_name = "LangChain DeepAgents"
    description = "Planning-first harness with a virtual filesystem and delegated subagents."

    async def stream(self, ctx: RunContext) -> AsyncIterator[AgentEvent]:
        tool_user_id.set(ctx.user_id)
        tool_document_ids.set(tuple(ctx.document_ids))
        run_id = str(ctx.run_id)

        yield AgentEvent(EventType.RUN_STARTED, {"framework": self.framework.value}, agent="orchestrator",
                         run_id=run_id)
        try:
            try:
                from deepagents import create_deep_agent
            except ImportError as exc:  # pragma: no cover
                raise FrameworkNotAvailableError("deepagents is not installed. `pip install deepagents`") from exc

            model = build_chat_model(
                ModelSpec(provider=ctx.provider, model=ctx.model, temperature=ctx.temperature,
                          max_tokens=ctx.max_tokens)
            )
            enabled = specs_for(ctx.enabled_agents)

            # Every tool any specialist might need must exist on the parent, since
            # declarative subagents inherit the parent's tool surface.
            all_tool_names = sorted({t for spec in enabled for t in spec.tools})
            tools = langchain_tools(all_tool_names)

            # Build a name→tool lookup so subagents get real tool objects.
            tool_lookup = {t.name: t for t in tools}

            subagents = [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "system_prompt": spec.instruction,
                    "tools": [tool_lookup[t] for t in spec.tools if t in tool_lookup],
                }
                for spec in enabled
                if spec.name != "writer"  # the main agent writes the final answer itself
            ]

            memory_block = ctx.memory_block()
            instructions = ORCHESTRATOR_INSTRUCTION + (
                f"\n\n{memory_block}" if memory_block else ""
            ) + (
                "\n\nWorkflow guidance for this harness:\n"
                "- Start by writing a short plan with the todo tool. Keep it to 3-5 items.\n"
                "- Delegate gathering work to subagents with the task tool; do not do their searching yourself.\n"
                "- Save long intermediate material to the virtual filesystem instead of carrying it in context.\n"
                "- You compose the final answer yourself, with citations intact."
            )

            agent = create_deep_agent(
                model=model,
                tools=tools,
                system_prompt=instructions,
                subagents=subagents,
            )

            history = [{"role": m["role"], "content": m["content"]} for m in ctx.history]
            payload = {"messages": history + [{"role": "user", "content": ctx.message}]}

            final_text = ""
            citations: list[dict[str, Any]] = []
            seen: set[str] = set()

            async for mode, chunk in agent.astream(payload, stream_mode=["updates", "messages"]):
                if mode == "messages":
                    message, meta = chunk
                    # Only stream AI message tokens; skip tool results and
                    # internal planning output (todo lists, filesystem ops).
                    msg_type = getattr(message, "type", "")
                    if msg_type not in ("ai", "AIMessageChunk"):
                        continue
                    raw = getattr(message, "content", "")
                    # content can be a string or a list of content blocks
                    if isinstance(raw, list):
                        token = "".join(
                            p.get("text", "") for p in raw if isinstance(p, dict) and p.get("type") == "text"
                        )
                    elif isinstance(raw, str):
                        token = raw
                    else:
                        token = ""
                    if token:
                        final_text += token
                        yield AgentEvent(EventType.TOKEN, {"text": token}, agent="orchestrator", run_id=run_id)
                    continue

                for node, update in (chunk or {}).items():
                    # LangGraph may wrap values in Overwrite at any depth.
                    messages = _unwrap(update, "messages")
                    if not isinstance(messages, list):
                        continue
                    for message in messages:
                        for call in getattr(message, "tool_calls", None) or []:
                            name = call.get("name", "")
                            if name == "task":
                                target = call.get("args", {}).get("subagent_type", "subagent")
                                if target not in seen:
                                    seen.add(target)
                                    yield AgentEvent(EventType.AGENT_STARTED, {}, agent=target, run_id=run_id)
                                yield AgentEvent(
                                    EventType.HANDOFF,
                                    {"to": target,
                                     "instruction": str(call.get("args", {}).get("description", ""))[:400]},
                                    agent="orchestrator", run_id=run_id,
                                )
                            elif name in ("write_todos", "todo"):
                                todos = call.get("args", {}).get("todos", [])
                                yield AgentEvent(EventType.PLAN, {"plan": [str(t) for t in todos]},
                                                 agent="orchestrator", run_id=run_id)
                            else:
                                yield AgentEvent(EventType.TOOL_CALL, {"tool": name, "input": call.get("args", {})},
                                                 agent=node, run_id=run_id)

                        if getattr(message, "type", "") == "tool":
                            content = str(getattr(message, "content", ""))
                            yield AgentEvent(
                                EventType.TOOL_RESULT,
                                {"tool": getattr(message, "name", "tool"), "output": content[:800]},
                                agent=node, run_id=run_id,
                            )
                            citations.extend(_citations(content))
                        elif getattr(message, "type", "") == "ai":
                            text = _text(message)
                            if text:
                                final_text = text

            if citations:
                yield AgentEvent(EventType.CITATION, {"citations": citations}, agent="retriever", run_id=run_id)
            yield AgentEvent(EventType.RUN_FINISHED, {"text": final_text, "citations": citations},
                             agent="orchestrator", run_id=run_id)

        except FrameworkNotAvailableError as exc:
            yield AgentEvent(EventType.ERROR, {"message": exc.message, "code": exc.code}, run_id=run_id)
        except Exception as exc:
            log.exception("deepagents_run_failed")
            yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]}, run_id=run_id)


def _unwrap(obj: Any, key: str = "") -> Any:
    """Recursively strip LangGraph Overwrite wrappers."""
    while hasattr(obj, "value"):
        obj = obj.value
    if key and isinstance(obj, dict):
        val = obj.get(key, [])
        while hasattr(val, "value"):
            val = val.value
        return val if val is not None else []
    return obj


def _text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def _citations(payload: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    return [
        {"filename": p.get("filename"), "page": p.get("page"), "marker": p.get("citation")}
        for p in (data.get("passages") or [])
        if isinstance(p, dict)
    ]
