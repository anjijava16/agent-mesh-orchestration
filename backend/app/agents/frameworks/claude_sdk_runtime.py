"""Claude Agent SDK adapter.

The SDK gives us a full agent harness - context management, subagents, hooks,
in-process MCP tools - driven by ClaudeSDKClient. Three things matter for our
integration:

1. Tools are exposed as an *in-process* SDK MCP server (create_sdk_mcp_server),
   so a tool call executes in this event loop with no subprocess or IPC.
2. Our specialists become programmatic subagents via ClaudeAgentOptions, with
   the orchestrator instruction as the system prompt. Delegation happens through
   the built-in `Task` tool, which must be in allowed_tools or the orchestrator
   silently answers everything itself.
3. The SDK client is constructed and torn down inside this call, so the SDK
   session is single-shot. Our own short-term history replay in _render_prompt
   is the only continuity across turns - the SDK is not holding a session for us
   between requests.

Note this path talks to Claude models specifically; if the request selected an
OpenAI or Gemini model we say so plainly rather than silently substituting.

Concurrency note: tool_user_id / tool_document_ids are contextvars set in this
generator's body, which mutates the *caller's* context rather than an isolated
one. That is fine for one run per asyncio task. If you ever drive two runs from
the same task, bind these at the tool-server layer instead or the second run
will clobber the first run's identity and document scope.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import AgentEvent, AgentRuntime, EventType, RunContext
from app.agents.definitions import ORCHESTRATOR_INSTRUCTION, specs_for
from app.agents.tools.adapters import claude_sdk_server
from app.agents.tools.core import tool_document_ids, tool_user_id
from app.config import AgentFramework, ModelProvider, settings
from app.core.errors import FrameworkNotAvailableError
from app.core.logging import get_logger

log = get_logger(__name__)

MCP_PREFIX = "mcp__agentmesh__"

# The subagent dispatch tool. Without this in allowed_tools the orchestrator
# cannot delegate and every AgentDefinition below is dead weight.
TASK_TOOL = "Task"

# Built-ins that permission_mode="bypassPermissions" would otherwise
# auto-approve. bypassPermissions covers approval, not availability - these have
# to be denied by name.
BUILTIN_DENYLIST = (
    "Bash",
    "BashOutput",
    "KillShell",
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Glob",
    "Grep",
    "WebSearch",
    "WebFetch",
)

# Rough character budget for the replayed history window, so a conversation with
# a pasted document in it does not blow the prompt.
HISTORY_TURNS = 10
HISTORY_CHAR_BUDGET = 12_000
PER_MESSAGE_CHAR_CAP = 2_000


class ClaudeAgentSDKRuntime(AgentRuntime):
    framework = AgentFramework.CLAUDE_AGENT_SDK
    display_name = "Claude Agent SDK"
    description = "Anthropic's agent harness with programmatic subagents and in-process MCP tools."

    async def stream(self, ctx: RunContext) -> AsyncIterator[AgentEvent]:
        tool_user_id.set(ctx.user_id)
        tool_document_ids.set(tuple(ctx.document_ids))
        run_id = str(ctx.run_id)

        yield AgentEvent(EventType.RUN_STARTED, {"framework": self.framework.value}, agent="orchestrator",
                         run_id=run_id)
        try:
            try:
                from claude_agent_sdk import (
                    AgentDefinition,
                    AssistantMessage,
                    ClaudeAgentOptions,
                    ClaudeSDKClient,
                    ResultMessage,
                    TextBlock,
                    ToolResultBlock,
                    ToolUseBlock,
                )
            except ImportError as exc:  # pragma: no cover
                raise FrameworkNotAvailableError(
                    "claude-agent-sdk is not installed. `pip install claude-agent-sdk`"
                ) from exc

            # The SDK also needs the Node CLI on PATH. Missing-CLI and transport
            # failures raise at __aenter__, well past the import guard above, so
            # pull the concrete types in when available and fall back to a
            # never-matching tuple on older SDK versions.
            try:
                from claude_agent_sdk import CLIConnectionError, CLINotFoundError, ProcessError

                startup_errors: tuple[type[BaseException], ...] = (
                    CLINotFoundError,
                    CLIConnectionError,
                    ProcessError,
                )
            except ImportError:  # pragma: no cover - older SDK
                startup_errors = ()

            if not settings.anthropic_api_key:
                raise FrameworkNotAvailableError("ANTHROPIC_API_KEY is required for the Claude Agent SDK runtime.")

            if ctx.provider is not ModelProvider.ANTHROPIC:
                yield AgentEvent(
                    EventType.ERROR,
                    {
                        "message": (
                            f"The Claude Agent SDK runs Claude models. You selected "
                            f"{ctx.provider.value}/{ctx.model}. Switch the model to Claude, or pick another "
                            f"framework for that provider."
                        ),
                        "code": "provider_mismatch",
                    },
                    run_id=run_id,
                )
                return

            specs = specs_for(ctx.enabled_agents)
            if not specs:
                raise FrameworkNotAvailableError(
                    "No specialists are enabled for this run; the Claude Agent SDK runtime has nothing to dispatch."
                )

            tool_names = sorted({t for spec in specs for t in spec.tools})
            mcp_server = claude_sdk_server(tool_names)

            # Task first: it is what lets the orchestrator reach the subagents.
            allowed = [TASK_TOOL] + [f"{MCP_PREFIX}{name}" for name in tool_names]

            memory_block = ctx.memory_block()
            system_prompt = ORCHESTRATOR_INSTRUCTION + (f"\n\n{memory_block}" if memory_block else "")

            # Subagents get the same memory the orchestrator does. Without this a
            # specialist runs with no user context at all.
            agents_config = {
                spec.name: AgentDefinition(
                    description=spec.description,
                    prompt=spec.instruction + (f"\n\n{memory_block}" if memory_block else ""),
                    tools=[f"{MCP_PREFIX}{t}" for t in spec.tools],
                    model="inherit",
                )
                for spec in specs
            }

            options = ClaudeAgentOptions(
                model=_normalize_model(ctx.model),
                system_prompt=system_prompt,
                mcp_servers={"agentmesh": mcp_server},
                allowed_tools=allowed,
                disallowed_tools=list(BUILTIN_DENYLIST),
                agents=agents_config,
                max_turns=settings.agent.max_orchestrator_steps,
                permission_mode="bypassPermissions",  # our MCP tools are already guarded; built-ins are denied above
                setting_sources=[],                    # no filesystem settings leakage
                env={"ANTHROPIC_API_KEY": settings.anthropic_api_key},  # the CLI subprocess has its own env
            )

            prompt = _render_prompt(ctx)
            final_text = ""
            citations: list[dict[str, Any]] = []
            seen_citations: set[tuple[Any, Any, Any]] = set()

            # tool_use_id of a Task call -> subagent name, so we can attribute
            # messages that arrive with parent_tool_use_id set.
            task_owner: dict[str, str] = {}
            started: set[str] = set()
            open_tasks: set[str] = set()

            try:
                async with ClaudeSDKClient(options=options) as client:
                    await client.query(prompt)

                    async for message in client.receive_response():
                        if isinstance(message, AssistantMessage):
                            parent = getattr(message, "parent_tool_use_id", None)
                            author = task_owner.get(parent, "orchestrator") if parent else "orchestrator"
                            is_orchestrator = parent is None

                            for block in message.content:
                                if isinstance(block, TextBlock) and block.text:
                                    # Only the orchestrator's own text is the
                                    # answer. Subagent reasoning streams to the
                                    # UI but must not land in final_text.
                                    if is_orchestrator:
                                        final_text += block.text
                                    yield AgentEvent(EventType.TOKEN, {"text": block.text}, agent=author,
                                                     run_id=run_id)

                                elif isinstance(block, ToolUseBlock):
                                    name = block.name
                                    if name == TASK_TOOL:
                                        target = str(block.input.get("subagent_type", "subagent"))
                                        tool_use_id = getattr(block, "id", None)
                                        if tool_use_id:
                                            task_owner[tool_use_id] = target
                                            open_tasks.add(tool_use_id)
                                        if target not in started:
                                            started.add(target)
                                            yield AgentEvent(EventType.AGENT_STARTED, {}, agent=target,
                                                             run_id=run_id)
                                        yield AgentEvent(EventType.HANDOFF, {"to": target}, agent=author,
                                                         run_id=run_id)
                                    else:
                                        yield AgentEvent(
                                            EventType.TOOL_CALL,
                                            {"tool": name.replace(MCP_PREFIX, ""), "input": block.input},
                                            agent=author, run_id=run_id,
                                        )

                                elif isinstance(block, ToolResultBlock):
                                    payload = _block_text(block)
                                    result_id = getattr(block, "tool_use_id", None)

                                    if result_id in open_tasks:
                                        open_tasks.discard(result_id)
                                        yield AgentEvent(EventType.AGENT_FINISHED, {},
                                                         agent=task_owner.get(result_id, "subagent"), run_id=run_id)
                                    else:
                                        yield AgentEvent(EventType.TOOL_RESULT, {"output": payload[:800]},
                                                         agent=author, run_id=run_id)

                                    for cite in _citations(payload):
                                        key = (cite["filename"], cite["page"], cite["marker"])
                                        if key not in seen_citations:
                                            seen_citations.add(key)
                                            citations.append(cite)

                        elif isinstance(message, ResultMessage):
                            yield AgentEvent(EventType.USAGE, _usage(message), agent="orchestrator", run_id=run_id)

                            failure = _failure_reason(message)
                            if failure:
                                yield AgentEvent(
                                    EventType.ERROR,
                                    {"message": failure, "code": "run_incomplete", "partial_text": final_text},
                                    agent="orchestrator", run_id=run_id,
                                )
                                return

                            if getattr(message, "result", None):
                                final_text = final_text or str(message.result)

            except startup_errors as exc:  # type: ignore[misc]
                raise FrameworkNotAvailableError(
                    f"Could not start the Claude Agent SDK CLI ({type(exc).__name__}: {exc}). "
                    "Check that the `claude` CLI is installed and on PATH."
                ) from exc

            # Any subagent whose result we never saw - close it out so the UI
            # is not left with a spinner.
            for tool_use_id in sorted(open_tasks):
                yield AgentEvent(EventType.AGENT_FINISHED, {"incomplete": True},
                                 agent=task_owner.get(tool_use_id, "subagent"), run_id=run_id)

            if citations:
                yield AgentEvent(EventType.CITATION, {"citations": citations}, agent="retriever", run_id=run_id)
            yield AgentEvent(EventType.RUN_FINISHED, {"text": final_text, "citations": citations},
                             agent="orchestrator", run_id=run_id)

        except FrameworkNotAvailableError as exc:
            yield AgentEvent(EventType.ERROR, {"message": exc.message, "code": exc.code}, run_id=run_id)
        except Exception as exc:
            log.exception("claude_sdk_run_failed")
            yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]}, run_id=run_id)


def _normalize_model(model: str) -> str:
    """Strip any provider prefix we carry internally. The SDK wants a bare model id."""
    return model.split("/", 1)[1] if "/" in model else model


def _render_prompt(ctx: RunContext) -> str:
    """The SDK session does not survive this call, so we replay our short-term
    window ourselves. Budgeted, because history can contain pasted documents."""
    if not ctx.history:
        return ctx.message

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

    if not lines:
        return ctx.message
    transcript = "\n".join(reversed(lines))
    return f"Conversation so far:\n{transcript}\n\nCurrent request:\n{ctx.message}"


def _block_text(block: Any) -> str:
    content = getattr(block, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def _usage(message: Any) -> dict[str, Any]:
    """usage is a dict on some SDK versions and an object on others; cache tokens
    are billed and must not be dropped."""
    raw = getattr(message, "usage", None) or {}

    def field(name: str) -> int:
        value = raw.get(name) if isinstance(raw, dict) else getattr(raw, name, 0)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    payload: dict[str, Any] = {
        "input_tokens": field("input_tokens"),
        "output_tokens": field("output_tokens"),
        "cache_creation_input_tokens": field("cache_creation_input_tokens"),
        "cache_read_input_tokens": field("cache_read_input_tokens"),
    }
    cost = getattr(message, "total_cost_usd", None)
    if cost is not None:
        payload["total_cost_usd"] = cost
    return payload


def _failure_reason(message: Any) -> str | None:
    """A run that hits max_turns or errors still yields a ResultMessage. Without
    this check a truncated run is indistinguishable from a successful one."""
    if getattr(message, "is_error", False):
        return f"The agent run ended with an error: {getattr(message, 'result', 'no detail provided')}"

    subtype = getattr(message, "subtype", None)
    if subtype in (None, "success"):
        return None
    if subtype == "error_max_turns":
        return (
            f"The agent hit its step limit ({settings.agent.max_orchestrator_steps}) before finishing. "
            "The partial answer is included; raise max_orchestrator_steps or narrow the request."
        )
    return f"The agent run ended early ({subtype})."


def _citations(payload: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    return [
        {"filename": p.get("filename"), "page": p.get("page"), "marker": p.get("citation")}
        for p in (data.get("passages") or [])
        if isinstance(p, dict)
    ]
# """Claude Agent SDK adapter.

# The SDK gives us a full agent harness - context management, subagents, hooks,
# in-process MCP tools - driven by ClaudeSDKClient. Two things matter for our
# integration:

# 1. Tools are exposed as an *in-process* SDK MCP server (create_sdk_mcp_server),
#    so a tool call executes in this event loop with no subprocess or IPC.
# 2. Our five specialists become programmatic subagents via ClaudeAgentOptions,
#    with the orchestrator instruction as the system prompt.

# Note this path talks to Claude models specifically; if the request selected an
# OpenAI or Gemini model we say so plainly rather than silently substituting.
# """
# from __future__ import annotations

# import json
# from collections.abc import AsyncIterator
# from typing import Any

# from app.agents.base import AgentEvent, AgentRuntime, EventType, RunContext
# from app.agents.definitions import ORCHESTRATOR_INSTRUCTION, specs_for
# from app.agents.tools.adapters import claude_sdk_server
# from app.agents.tools.core import tool_document_ids, tool_user_id
# from app.config import AgentFramework, ModelProvider, settings
# from app.core.errors import FrameworkNotAvailableError
# from app.core.logging import get_logger

# log = get_logger(__name__)


# class ClaudeAgentSDKRuntime(AgentRuntime):
#     framework = AgentFramework.CLAUDE_AGENT_SDK
#     display_name = "Claude Agent SDK"
#     description = "Anthropic's agent harness with programmatic subagents and in-process MCP tools."

#     async def stream(self, ctx: RunContext) -> AsyncIterator[AgentEvent]:
#         tool_user_id.set(ctx.user_id)
#         tool_document_ids.set(tuple(ctx.document_ids))
#         run_id = str(ctx.run_id)

#         yield AgentEvent(EventType.RUN_STARTED, {"framework": self.framework.value}, agent="orchestrator",
#                          run_id=run_id)
#         try:
#             try:
#                 from claude_agent_sdk import (
#                     AgentDefinition,
#                     AssistantMessage,
#                     ClaudeAgentOptions,
#                     ClaudeSDKClient,
#                     ResultMessage,
#                     TextBlock,
#                     ToolResultBlock,
#                     ToolUseBlock,
#                 )
#             except ImportError as exc:  # pragma: no cover
#                 raise FrameworkNotAvailableError(
#                     "claude-agent-sdk is not installed. `pip install claude-agent-sdk`"
#                 ) from exc

#             if not settings.anthropic_api_key:
#                 raise FrameworkNotAvailableError("ANTHROPIC_API_KEY is required for the Claude Agent SDK runtime.")

#             if ctx.provider is not ModelProvider.ANTHROPIC:
#                 yield AgentEvent(
#                     EventType.ERROR,
#                     {
#                         "message": (
#                             f"The Claude Agent SDK runs Claude models. You selected "
#                             f"{ctx.provider.value}/{ctx.model}. Switch the model to Claude, or pick another "
#                             f"framework for that provider."
#                         ),
#                         "code": "provider_mismatch",
#                     },
#                     run_id=run_id,
#                 )
#                 return

#             specs = specs_for(ctx.enabled_agents)
#             tool_names = sorted({t for spec in specs for t in spec.tools})
#             mcp_server = claude_sdk_server(tool_names)
#             allowed = [f"mcp__agentmesh__{name}" for name in tool_names]

#             agents_config = {
#                 spec.name: AgentDefinition(
#                     description=spec.description,
#                     prompt=spec.instruction,
#                     tools=[f"mcp__agentmesh__{t}" for t in spec.tools],
#                     model="inherit",
#                 )
#                 for spec in specs
#             }

#             memory_block = ctx.memory_block()
#             system_prompt = ORCHESTRATOR_INSTRUCTION + (f"\n\n{memory_block}" if memory_block else "")

#             options = ClaudeAgentOptions(
#                 model=ctx.model,
#                 system_prompt=system_prompt,
#                 mcp_servers={"agentmesh": mcp_server},
#                 allowed_tools=allowed,
#                 agents=agents_config,
#                 max_turns=settings.agent.max_orchestrator_steps,
#                 permission_mode="bypassPermissions",  # tools are ours, already guarded
#                 setting_sources=[],                    # no filesystem settings leakage
#             )

#             prompt = _render_prompt(ctx)
#             final_text = ""
#             citations: list[dict[str, Any]] = []
#             seen: set[str] = set()

#             async with ClaudeSDKClient(options=options) as client:
#                 await client.query(prompt)

#                 async for message in client.receive_response():
#                     if isinstance(message, AssistantMessage):
#                         author = getattr(message, "subtype", None) or "orchestrator"
#                         for block in message.content:
#                             if isinstance(block, TextBlock) and block.text:
#                                 final_text += block.text
#                                 yield AgentEvent(EventType.TOKEN, {"text": block.text}, agent=author, run_id=run_id)
#                             elif isinstance(block, ToolUseBlock):
#                                 name = block.name.replace("mcp__agentmesh__", "")
#                                 if name == "Task":
#                                     target = str(block.input.get("subagent_type", "subagent"))
#                                     if target not in seen:
#                                         seen.add(target)
#                                         yield AgentEvent(EventType.AGENT_STARTED, {}, agent=target, run_id=run_id)
#                                     yield AgentEvent(EventType.HANDOFF, {"to": target}, agent="orchestrator",
#                                                      run_id=run_id)
#                                 else:
#                                     yield AgentEvent(EventType.TOOL_CALL, {"tool": name, "input": block.input},
#                                                      agent=author, run_id=run_id)
#                             elif isinstance(block, ToolResultBlock):
#                                 payload = _block_text(block)
#                                 yield AgentEvent(EventType.TOOL_RESULT, {"output": payload[:800]}, agent=author,
#                                                  run_id=run_id)
#                                 citations.extend(_citations(payload))

#                     elif isinstance(message, ResultMessage):
#                         usage = getattr(message, "usage", None) or {}
#                         yield AgentEvent(
#                             EventType.USAGE,
#                             {
#                                 "input_tokens": int(usage.get("input_tokens", 0) or 0),
#                                 "output_tokens": int(usage.get("output_tokens", 0) or 0),
#                             },
#                             agent="orchestrator", run_id=run_id,
#                         )
#                         if getattr(message, "result", None):
#                             final_text = final_text or str(message.result)

#             if citations:
#                 yield AgentEvent(EventType.CITATION, {"citations": citations}, agent="retriever", run_id=run_id)
#             yield AgentEvent(EventType.RUN_FINISHED, {"text": final_text, "citations": citations},
#                              agent="orchestrator", run_id=run_id)

#         except FrameworkNotAvailableError as exc:
#             yield AgentEvent(EventType.ERROR, {"message": exc.message, "code": exc.code}, run_id=run_id)
#         except Exception as exc:
#             log.exception("claude_sdk_run_failed")
#             yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]}, run_id=run_id)


# def _render_prompt(ctx: RunContext) -> str:
#     """The SDK owns its own session, but we still replay our short-term window so
#     a framework switch mid-conversation does not lose the thread."""
#     if not ctx.history:
#         return ctx.message
#     transcript = "\n".join(f"{m['role']}: {m['content']}" for m in ctx.history[-10:])
#     return f"Conversation so far:\n{transcript}\n\nCurrent request:\n{ctx.message}"


# def _block_text(block: Any) -> str:
#     content = getattr(block, "content", "")
#     if isinstance(content, str):
#         return content
#     if isinstance(content, list):
#         return "".join(part.get("text", "") for part in content if isinstance(part, dict))
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
