"""Claude Agent SDK adapter.

The SDK gives us a full agent harness - context management, subagents, hooks,
in-process MCP tools - driven by ClaudeSDKClient. Two things matter for our
integration:

1. Tools are exposed as an *in-process* SDK MCP server (create_sdk_mcp_server),
   so a tool call executes in this event loop with no subprocess or IPC.
2. Our five specialists become programmatic subagents via ClaudeAgentOptions,
   with the orchestrator instruction as the system prompt.

Note this path talks to Claude models specifically; if the request selected an
OpenAI or Gemini model we say so plainly rather than silently substituting.
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
            tool_names = sorted({t for spec in specs for t in spec.tools})
            mcp_server = claude_sdk_server(tool_names)
            allowed = [f"mcp__agentmesh__{name}" for name in tool_names]

            agents_config = {
                spec.name: AgentDefinition(
                    description=spec.description,
                    prompt=spec.instruction,
                    tools=[f"mcp__agentmesh__{t}" for t in spec.tools],
                    model="inherit",
                )
                for spec in specs
            }

            memory_block = ctx.memory_block()
            system_prompt = ORCHESTRATOR_INSTRUCTION + (f"\n\n{memory_block}" if memory_block else "")

            options = ClaudeAgentOptions(
                model=ctx.model,
                system_prompt=system_prompt,
                mcp_servers={"agentmesh": mcp_server},
                allowed_tools=allowed,
                agents=agents_config,
                max_turns=settings.agent.max_orchestrator_steps,
                permission_mode="bypassPermissions",  # tools are ours, already guarded
                setting_sources=[],                    # no filesystem settings leakage
            )

            prompt = _render_prompt(ctx)
            final_text = ""
            citations: list[dict[str, Any]] = []
            seen: set[str] = set()

            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)

                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        author = getattr(message, "subtype", None) or "orchestrator"
                        for block in message.content:
                            if isinstance(block, TextBlock) and block.text:
                                final_text += block.text
                                yield AgentEvent(EventType.TOKEN, {"text": block.text}, agent=author, run_id=run_id)
                            elif isinstance(block, ToolUseBlock):
                                name = block.name.replace("mcp__agentmesh__", "")
                                if name == "Task":
                                    target = str(block.input.get("subagent_type", "subagent"))
                                    if target not in seen:
                                        seen.add(target)
                                        yield AgentEvent(EventType.AGENT_STARTED, {}, agent=target, run_id=run_id)
                                    yield AgentEvent(EventType.HANDOFF, {"to": target}, agent="orchestrator",
                                                     run_id=run_id)
                                else:
                                    yield AgentEvent(EventType.TOOL_CALL, {"tool": name, "input": block.input},
                                                     agent=author, run_id=run_id)
                            elif isinstance(block, ToolResultBlock):
                                payload = _block_text(block)
                                yield AgentEvent(EventType.TOOL_RESULT, {"output": payload[:800]}, agent=author,
                                                 run_id=run_id)
                                citations.extend(_citations(payload))

                    elif isinstance(message, ResultMessage):
                        usage = getattr(message, "usage", None) or {}
                        yield AgentEvent(
                            EventType.USAGE,
                            {
                                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                                "output_tokens": int(usage.get("output_tokens", 0) or 0),
                            },
                            agent="orchestrator", run_id=run_id,
                        )
                        if getattr(message, "result", None):
                            final_text = final_text or str(message.result)

            if citations:
                yield AgentEvent(EventType.CITATION, {"citations": citations}, agent="retriever", run_id=run_id)
            yield AgentEvent(EventType.RUN_FINISHED, {"text": final_text, "citations": citations},
                             agent="orchestrator", run_id=run_id)

        except FrameworkNotAvailableError as exc:
            yield AgentEvent(EventType.ERROR, {"message": exc.message, "code": exc.code}, run_id=run_id)
        except Exception as exc:
            log.exception("claude_sdk_run_failed")
            yield AgentEvent(EventType.ERROR, {"message": f"{type(exc).__name__}: {exc}"[:600]}, run_id=run_id)


def _render_prompt(ctx: RunContext) -> str:
    """The SDK owns its own session, but we still replay our short-term window so
    a framework switch mid-conversation does not lose the thread."""
    if not ctx.history:
        return ctx.message
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in ctx.history[-10:])
    return f"Conversation so far:\n{transcript}\n\nCurrent request:\n{ctx.message}"


def _block_text(block: Any) -> str:
    content = getattr(block, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
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
