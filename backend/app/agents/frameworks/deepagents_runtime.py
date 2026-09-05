"""LangChain DeepAgents adapter.

DeepAgents is the opposite philosophy to the ADK pipeline: instead of declaring
the workflow, you give one capable agent a planning tool, a virtual filesystem
and a roster of subagents, and let it decide. It is the right choice for
open-ended research where the shape of the work is not known in advance.

Our specialists map onto declarative subagent specs. The main agent gets the
orchestrator instruction and the `task` tool that spawns them.

Two things about this harness shape the code below:

1. Subagents run as LangGraph subgraphs. We stream with subgraphs=True so their
   tokens and tool calls carry a namespace we can attribute; without it every
   token looks like it came from the orchestrator and subagent reasoning lands
   in the final answer.
2. The virtual filesystem lives in graph state, not on disk. Nothing persists
   between runs unless a checkpointer is supplied, so we surface the final file
   set on RUN_FINISHED rather than letting it evaporate.

Concurrency note: tool_user_id / tool_document_ids are contextvars set in this
generator's body, which mutates the caller's context rather than an isolated
one. Fine for one run per asyncio task; bind at the tool layer if that ever
stops being true.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import AgentEvent, AgentRuntime, EventType, RunContext
from app.agents.definitions import ORCHESTRATOR_INSTRUCTION, specs_for
from app.agents.tools.adapters import langchain_tools
from app.agents.tools.core import tool_document_ids, tool_user_id
from app.config import AgentFramework, settings
from app.core.errors import FrameworkNotAvailableError
from app.core.logging import get_logger
from app.llm.registry import ModelSpec, build_chat_model

log = get_logger(__name__)

# The main agent composes the final answer, so it is never spawned as a subagent.
MAIN_AGENT_ROLE = "writer"

# Built-in DeepAgents tools we recognise for event mapping.
TASK_TOOL = "task"
TODO_TOOLS = ("write_todos", "todo")
FILESYSTEM_TOOLS = ("write_file", "read_file", "ls", "edit_file")

HISTORY_TURNS = 12
HISTORY_CHAR_BUDGET = 16_000
PER_MESSAGE_CHAR_CAP = 3_000


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
            if not enabled:
                raise FrameworkNotAvailableError(
                    "No specialists are enabled for this run; DeepAgents has nothing to delegate to."
                )

            # Every tool any specialist might need must exist on the parent, since
            # declarative subagents inherit the parent's tool surface.
            all_tool_names = sorted({t for spec in enabled for t in spec.tools})
            tools = langchain_tools(all_tool_names)
            tool_lookup = {t.name: t for t in tools}

            # A tool a spec asks for but the adapter did not build is a config bug,
            # not something to silently drop - the specialist would run crippled.
            missing = sorted(set(all_tool_names) - set(tool_lookup))
            if missing:
                raise FrameworkNotAvailableError(
                    f"langchain_tools did not return: {', '.join(missing)}. "
                    "Check the tool adapter registry against the agent definitions."
                )

            memory_block = ctx.memory_block()

            # Subagents get the same memory the orchestrator does. Without this a
            # specialist runs with no user context at all.
            prompt_key = _subagent_prompt_key()
            subagents = [
                {
                    "name": spec.name,
                    "description": spec.description,
                    prompt_key: spec.instruction + (f"\n\n{memory_block}" if memory_block else ""),
                    "tools": [tool_lookup[t] for t in spec.tools],
                }
                for spec in enabled
                if spec.name != MAIN_AGENT_ROLE
            ]
            subagent_names = {s["name"] for s in subagents}

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

            payload = {"messages": _render_messages(ctx)}

            # LangGraph defaults to 25 steps. A planning agent that delegates
            # three times blows through that and raises GraphRecursionError,
            # which would otherwise surface as an opaque class name.
            config: dict[str, Any] = {
                "recursion_limit": getattr(settings.agent, "max_graph_steps", 60),
                "configurable": {"thread_id": run_id, "user_id": ctx.user_id},
            }

            streamed_text = ""       # tokens from the main agent only
            final_message_text = ""  # last complete main-agent AI message
            citations: list[dict[str, Any]] = []
            seen_citations: set[tuple[Any, Any, Any]] = set()
            started: set[str] = set()
            open_subagents: set[str] = set()
            usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}
            files: dict[str, Any] = {}

            timeout = getattr(settings.agent, "run_timeout_seconds", None)
            stream = agent.astream(payload, config=config, stream_mode=["updates", "messages"], subgraphs=True)

            async for event in _with_timeout(stream, timeout):
                namespace, mode, chunk = _unpack(event)
                origin = _origin(namespace, subagent_names)
                is_main = origin == "orchestrator"

                if mode == "messages":
                    message, meta = chunk if isinstance(chunk, tuple) else (chunk, {})
                    # Only stream AI message tokens; skip tool results and
                    # internal planning output (todo lists, filesystem ops).
                    if getattr(message, "type", "") not in ("ai", "AIMessageChunk"):
                        continue
                    token = _text(message)
                    if not token:
                        continue
                    # Subagent tokens stream to the UI under their own name but
                    # must never accumulate into the final answer.
                    if is_main:
                        streamed_text += token
                    agent_name = origin if not is_main else _node_agent(meta, "orchestrator")
                    yield AgentEvent(EventType.TOKEN, {"text": token}, agent=agent_name, run_id=run_id)
                    continue

                for node, update in (chunk or {}).items():
                    # LangGraph may wrap values in Overwrite at any depth.
                    state_files = _unwrap(update, "files")
                    if isinstance(state_files, dict) and state_files:
                        files.update(state_files)

                    messages = _unwrap(update, "messages")
                    if not isinstance(messages, list):
                        continue

                    for message in messages:
                        _accumulate_usage(usage, message)

                        for call in getattr(message, "tool_calls", None) or []:
                            name = call.get("name", "")
                            args = call.get("args", {}) or {}

                            if name == TASK_TOOL:
                                target = str(args.get("subagent_type", "subagent"))
                                if target not in started:
                                    started.add(target)
                                    yield AgentEvent(EventType.AGENT_STARTED, {}, agent=target, run_id=run_id)
                                open_subagents.add(target)
                                yield AgentEvent(
                                    EventType.HANDOFF,
                                    {"to": target, "instruction": str(args.get("description", ""))[:400]},
                                    agent=origin, run_id=run_id,
                                )
                            elif name in TODO_TOOLS:
                                yield AgentEvent(EventType.PLAN, {"plan": _format_todos(args.get("todos", []))},
                                                 agent=origin, run_id=run_id)
                            else:
                                yield AgentEvent(EventType.TOOL_CALL, {"tool": name, "input": args},
                                                 agent=origin, run_id=run_id)

                        msg_type = getattr(message, "type", "")

                        if msg_type == "tool":
                            tool_name = getattr(message, "name", "tool")
                            content = str(getattr(message, "content", ""))

                            if tool_name == TASK_TOOL:
                                # A task result means that subagent finished.
                                finished = next(iter(open_subagents), "subagent")
                                open_subagents.discard(finished)
                                yield AgentEvent(EventType.AGENT_FINISHED, {}, agent=finished, run_id=run_id)
                            else:
                                yield AgentEvent(
                                    EventType.TOOL_RESULT,
                                    {"tool": tool_name, "output": content[:800]},
                                    agent=origin, run_id=run_id,
                                )

                            for cite in _citations(content):
                                key = (cite["filename"], cite["page"], cite["marker"])
                                if key not in seen_citations:
                                    seen_citations.add(key)
                                    citations.append(cite)

                        elif msg_type == "ai" and is_main:
                            # Only the main agent's completed messages are
                            # candidates for the final answer.
                            text = _text(message)
                            if text:
                                final_message_text = text

            for name in sorted(open_subagents):
                yield AgentEvent(EventType.AGENT_FINISHED, {"incomplete": True}, agent=name, run_id=run_id)

            yield AgentEvent(EventType.USAGE, usage, agent="orchestrator", run_id=run_id)

            if citations:
                yield AgentEvent(EventType.CITATION, {"citations": citations}, agent="retriever", run_id=run_id)

            final_text = final_message_text or streamed_text
            yield AgentEvent(
                EventType.RUN_FINISHED,
                {"text": final_text, "citations": citations, "files": sorted(files)},
                agent="orchestrator", run_id=run_id,
            )

        except asyncio.CancelledError:
            # Client disconnects must propagate, not be swallowed as a run error.
            raise
        except FrameworkNotAvailableError as exc:
            yield AgentEvent(EventType.ERROR, {"message": exc.message, "code": exc.code}, run_id=run_id)
        except asyncio.TimeoutError:
            yield AgentEvent(
                EventType.ERROR,
                {"message": "The agent run exceeded its time budget.", "code": "run_timeout"},
                run_id=run_id,
            )
        except Exception as exc:
            log.exception("deepagents_run_failed")
            if type(exc).__name__ == "GraphRecursionError":
                yield AgentEvent(
                    EventType.ERROR,
                    {
                        "message": (
                            "The agent hit its step limit before finishing. Raise "
                            "settings.agent.max_graph_steps or narrow the request."
                        ),
                        "code": "recursion_limit",
                    },
                    run_id=run_id,
                )
                return
            yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]}, run_id=run_id)


async def _with_timeout(stream: AsyncIterator[Any], seconds: float | None) -> AsyncIterator[Any]:
    """Per-chunk timeout. A whole-run timeout would kill long legitimate runs;
    this catches a stalled provider instead."""
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


def _unpack(event: Any) -> tuple[tuple[str, ...], str, Any]:
    """subgraphs=True with a list stream_mode yields (namespace, mode, chunk);
    older versions yield (mode, chunk). Handle both."""
    if isinstance(event, tuple) and len(event) == 3:
        namespace, mode, chunk = event
        return tuple(namespace or ()), mode, chunk
    if isinstance(event, tuple) and len(event) == 2:
        mode, chunk = event
        return (), mode, chunk
    return (), "updates", event


def _origin(namespace: tuple[str, ...], subagent_names: set[str]) -> str:
    """Map a LangGraph namespace path onto a specialist name. Namespace entries
    look like 'task:abc123' or the subagent node name."""
    for part in reversed(namespace):
        head = str(part).split(":", 1)[0]
        if head in subagent_names:
            return head
        for name in subagent_names:
            if name in str(part):
                return name
    return "orchestrator"


def _node_agent(meta: Any, default: str) -> str:
    if isinstance(meta, dict):
        node = meta.get("langgraph_node")
        if isinstance(node, str) and node:
            return default if node in ("agent", "model", "call_model") else default
    return default


def _subagent_prompt_key() -> str:
    """deepagents renamed the subagent prompt field between releases; passing the
    wrong key means the specialist silently runs with no instruction at all."""
    try:
        from deepagents import SubAgent  # type: ignore

        keys = set(getattr(SubAgent, "__annotations__", {}) or {})
        if "system_prompt" in keys:
            return "system_prompt"
        if "prompt" in keys:
            return "prompt"
    except Exception:  # pragma: no cover - version without the export
        pass
    return "system_prompt"


def _render_messages(ctx: RunContext) -> list[dict[str, str]]:
    """Bounded history replay. The raw history can contain pasted documents, so
    cap both per message and in total."""
    lines: list[dict[str, str]] = []
    used = 0
    for m in reversed(ctx.history[-HISTORY_TURNS:]):
        content = str(m.get("content", ""))
        if len(content) > PER_MESSAGE_CHAR_CAP:
            content = content[:PER_MESSAGE_CHAR_CAP] + " …[truncated]"
        if used + len(content) > HISTORY_CHAR_BUDGET:
            break
        lines.append({"role": m.get("role", "user"), "content": content})
        used += len(content)
    lines.reverse()
    return lines + [{"role": "user", "content": ctx.message}]


def _accumulate_usage(usage: dict[str, int], message: Any) -> None:
    meta = getattr(message, "usage_metadata", None)
    if not isinstance(meta, dict):
        return
    usage["input_tokens"] += int(meta.get("input_tokens", 0) or 0)
    usage["output_tokens"] += int(meta.get("output_tokens", 0) or 0)
    details = meta.get("input_token_details") or {}
    if isinstance(details, dict):
        usage["cache_read_input_tokens"] += int(details.get("cache_read", 0) or 0)


def _format_todos(todos: Any) -> list[str]:
    """Todos arrive as dicts with content/status; str() on those is unreadable."""
    out: list[str] = []
    for t in todos or []:
        if isinstance(t, dict):
            content = str(t.get("content") or t.get("task") or "").strip()
            status = str(t.get("status") or "").strip()
            out.append(f"[{status}] {content}" if status else content)
        else:
            out.append(str(t))
    return [t for t in out if t]


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
        return "".join(
            p.get("text", "") for p in content
            if isinstance(p, dict) and p.get("type", "text") == "text"
        )
    return str(content)


def _citations(payload: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    return [
        {"filename": p.get("filename"), "page": p.get("page"), "marker": p.get("citation")}
        for p in (data.get("passages") or [])
        if isinstance(p, dict)
    ]
# """LangChain DeepAgents adapter.

# DeepAgents is the opposite philosophy to the ADK pipeline: instead of declaring
# the workflow, you give one capable agent a planning tool, a virtual filesystem
# and a roster of subagents, and let it decide. It is the right choice for
# open-ended research where the shape of the work is not known in advance.

# Our five specialists map onto declarative subagent specs. The main agent gets
# the orchestrator instruction and the `task` tool that spawns them.
# """
# from __future__ import annotations

# import json
# from collections.abc import AsyncIterator
# from typing import Any

# from app.agents.base import AgentEvent, AgentRuntime, EventType, RunContext
# from app.agents.definitions import ORCHESTRATOR_INSTRUCTION, specs_for
# from app.agents.tools.adapters import langchain_tools
# from app.agents.tools.core import tool_document_ids, tool_user_id
# from app.config import AgentFramework
# from app.core.errors import FrameworkNotAvailableError
# from app.core.logging import get_logger
# from app.llm.registry import ModelSpec, build_chat_model

# log = get_logger(__name__)


# class DeepAgentsRuntime(AgentRuntime):
#     framework = AgentFramework.DEEPAGENTS
#     display_name = "LangChain DeepAgents"
#     description = "Planning-first harness with a virtual filesystem and delegated subagents."

#     async def stream(self, ctx: RunContext) -> AsyncIterator[AgentEvent]:
#         tool_user_id.set(ctx.user_id)
#         tool_document_ids.set(tuple(ctx.document_ids))
#         run_id = str(ctx.run_id)

#         yield AgentEvent(EventType.RUN_STARTED, {"framework": self.framework.value}, agent="orchestrator",
#                          run_id=run_id)
#         try:
#             try:
#                 from deepagents import create_deep_agent
#             except ImportError as exc:  # pragma: no cover
#                 raise FrameworkNotAvailableError("deepagents is not installed. `pip install deepagents`") from exc

#             model = build_chat_model(
#                 ModelSpec(provider=ctx.provider, model=ctx.model, temperature=ctx.temperature,
#                           max_tokens=ctx.max_tokens)
#             )
#             enabled = specs_for(ctx.enabled_agents)

#             # Every tool any specialist might need must exist on the parent, since
#             # declarative subagents inherit the parent's tool surface.
#             all_tool_names = sorted({t for spec in enabled for t in spec.tools})
#             tools = langchain_tools(all_tool_names)

#             # Build a name→tool lookup so subagents get real tool objects.
#             tool_lookup = {t.name: t for t in tools}

#             subagents = [
#                 {
#                     "name": spec.name,
#                     "description": spec.description,
#                     "system_prompt": spec.instruction,
#                     "tools": [tool_lookup[t] for t in spec.tools if t in tool_lookup],
#                 }
#                 for spec in enabled
#                 if spec.name != "writer"  # the main agent writes the final answer itself
#             ]

#             memory_block = ctx.memory_block()
#             instructions = ORCHESTRATOR_INSTRUCTION + (
#                 f"\n\n{memory_block}" if memory_block else ""
#             ) + (
#                 "\n\nWorkflow guidance for this harness:\n"
#                 "- Start by writing a short plan with the todo tool. Keep it to 3-5 items.\n"
#                 "- Delegate gathering work to subagents with the task tool; do not do their searching yourself.\n"
#                 "- Save long intermediate material to the virtual filesystem instead of carrying it in context.\n"
#                 "- You compose the final answer yourself, with citations intact."
#             )

#             agent = create_deep_agent(
#                 model=model,
#                 tools=tools,
#                 system_prompt=instructions,
#                 subagents=subagents,
#             )

#             history = [{"role": m["role"], "content": m["content"]} for m in ctx.history]
#             payload = {"messages": history + [{"role": "user", "content": ctx.message}]}

#             final_text = ""
#             citations: list[dict[str, Any]] = []
#             seen: set[str] = set()

#             async for mode, chunk in agent.astream(payload, stream_mode=["updates", "messages"]):
#                 if mode == "messages":
#                     message, meta = chunk
#                     # Only stream AI message tokens; skip tool results and
#                     # internal planning output (todo lists, filesystem ops).
#                     msg_type = getattr(message, "type", "")
#                     if msg_type not in ("ai", "AIMessageChunk"):
#                         continue
#                     raw = getattr(message, "content", "")
#                     # content can be a string or a list of content blocks
#                     if isinstance(raw, list):
#                         token = "".join(
#                             p.get("text", "") for p in raw if isinstance(p, dict) and p.get("type") == "text"
#                         )
#                     elif isinstance(raw, str):
#                         token = raw
#                     else:
#                         token = ""
#                     if token:
#                         final_text += token
#                         yield AgentEvent(EventType.TOKEN, {"text": token}, agent="orchestrator", run_id=run_id)
#                     continue

#                 for node, update in (chunk or {}).items():
#                     # LangGraph may wrap values in Overwrite at any depth.
#                     messages = _unwrap(update, "messages")
#                     if not isinstance(messages, list):
#                         continue
#                     for message in messages:
#                         for call in getattr(message, "tool_calls", None) or []:
#                             name = call.get("name", "")
#                             if name == "task":
#                                 target = call.get("args", {}).get("subagent_type", "subagent")
#                                 if target not in seen:
#                                     seen.add(target)
#                                     yield AgentEvent(EventType.AGENT_STARTED, {}, agent=target, run_id=run_id)
#                                 yield AgentEvent(
#                                     EventType.HANDOFF,
#                                     {"to": target,
#                                      "instruction": str(call.get("args", {}).get("description", ""))[:400]},
#                                     agent="orchestrator", run_id=run_id,
#                                 )
#                             elif name in ("write_todos", "todo"):
#                                 todos = call.get("args", {}).get("todos", [])
#                                 yield AgentEvent(EventType.PLAN, {"plan": [str(t) for t in todos]},
#                                                  agent="orchestrator", run_id=run_id)
#                             else:
#                                 yield AgentEvent(EventType.TOOL_CALL, {"tool": name, "input": call.get("args", {})},
#                                                  agent=node, run_id=run_id)

#                         if getattr(message, "type", "") == "tool":
#                             content = str(getattr(message, "content", ""))
#                             yield AgentEvent(
#                                 EventType.TOOL_RESULT,
#                                 {"tool": getattr(message, "name", "tool"), "output": content[:800]},
#                                 agent=node, run_id=run_id,
#                             )
#                             citations.extend(_citations(content))
#                         elif getattr(message, "type", "") == "ai":
#                             text = _text(message)
#                             if text:
#                                 final_text = text

#             if citations:
#                 yield AgentEvent(EventType.CITATION, {"citations": citations}, agent="retriever", run_id=run_id)
#             yield AgentEvent(EventType.RUN_FINISHED, {"text": final_text, "citations": citations},
#                              agent="orchestrator", run_id=run_id)

#         except FrameworkNotAvailableError as exc:
#             yield AgentEvent(EventType.ERROR, {"message": exc.message, "code": exc.code}, run_id=run_id)
#         except Exception as exc:
#             log.exception("deepagents_run_failed")
#             yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]}, run_id=run_id)


# def _unwrap(obj: Any, key: str = "") -> Any:
#     """Recursively strip LangGraph Overwrite wrappers."""
#     while hasattr(obj, "value"):
#         obj = obj.value
#     if key and isinstance(obj, dict):
#         val = obj.get(key, [])
#         while hasattr(val, "value"):
#             val = val.value
#         return val if val is not None else []
#     return obj


# def _text(message: Any) -> str:
#     content = getattr(message, "content", "")
#     if isinstance(content, str):
#         return content
#     if isinstance(content, list):
#         return "".join(p.get("text", "") for p in content if isinstance(p, dict))
#     return str(content)


# def _citations(payload: str) -> list[dict[str, Any]]:
#     try:
#         data = json.loads(payload)
#     except json.JSONDecodeError:
#         return []
#     return [
#         {"filename": p.get("filename"), "page": p.get("page"), "marker": p.get("citation")}
#         for p in (data.get("passages") or [])
#         if isinstance(p, dict)
#     ]
