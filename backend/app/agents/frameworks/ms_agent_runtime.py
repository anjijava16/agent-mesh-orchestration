"""Microsoft Agent Framework adapter — GroupChat orchestration.

The MS Agent Framework (``agent-framework-core`` + ``agent-framework-orchestrations``)
gives us a different flavour of multi-agent coordination: instead of a supervisor
graph or a declarative pipeline, all agents sit in a shared chat room and
iteratively refine each other's work until a termination condition fires.

Topology (GroupChat):

    ┌──────────────────────────────────────────────────┐
    │                  shared transcript               │
    │                                                  │
    │   Researcher ─> Retriever ─> Analyst ─>          │
    │   Compliance ─> Writer ─> Researcher ─> ...      │
    │                                                  │
    │   round-robin selection, terminates when Writer   │
    │   produces the final answer or after max rounds   │
    └──────────────────────────────────────────────────┘

Key design decisions:

1. **Custom BaseChatClient** — We implement the MS framework's ``BaseChatClient``
   interface using our existing openai 1.x SDK, so we do not need the separate
   ``agent-framework-openai`` package (which requires openai 2.x and conflicts
   with our pinned dependencies).  For Anthropic / Google models we route
   through LiteLLM's OpenAI-compatibility layer.

2. **Tool pre-execution** — The MS Agent Framework agents are pure LLM chat
   agents; they do not have a native tool-calling loop.  Our specialists that
   need tools get their tool results injected as context in their instructions.

3. **Streaming bridge** — ``GroupChatBuilder.build().run(task)`` is async and
   returns a result object.  We normalise the conversation messages into our
   ``AgentEvent`` stream.

4. **Speaker selection** — Round-robin through enabled agents, ordered:
   researcher -> retriever -> analyst -> compliance -> writer.

5. **Termination** — The chat ends when the Writer produces an answer (does not
   contain "REVISE"), or after a safety cap of ``2 * len(agents)`` messages.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Awaitable

from app.agents.base import AgentEvent, AgentRuntime, EventType, RunContext
from app.agents.definitions import AGENT_SPECS, ORCHESTRATOR_INSTRUCTION, specs_for
from app.agents.tools.core import TOOL_REGISTRY, tool_document_ids, tool_user_id
from app.config import AgentFramework, ModelProvider, settings
from app.core.errors import FrameworkNotAvailableError
from app.core.logging import get_logger
from app.llm.registry import ModelSpec

log = get_logger(__name__)

CITATION_RE = re.compile(r"\[[^\]]+ p\.\d+\]")

AGENT_ORDER = ("researcher", "retriever", "analyst", "compliance", "writer")
MAX_MESSAGES_FACTOR = 2
HISTORY_TURNS = 12
HISTORY_CHAR_BUDGET = 12_000
PER_MESSAGE_CHAR_CAP = 2_000


# ===================================================================
# Custom ChatClient wrapping our openai 1.x SDK
# ===================================================================

def _build_chat_client(spec: ModelSpec) -> Any:
    """Create a BaseChatClient implementation backed by our openai 1.x SDK.

    For OpenAI models we call the API directly.  For Anthropic / Google we
    route through LiteLLM which presents an OpenAI-compatible interface.
    """
    try:
        from agent_framework import (
            BaseChatClient,
            ChatResponse,
            Message,
        )
    except ImportError as exc:
        raise FrameworkNotAvailableError(
            "agent-framework-core is not installed. "
            "`pip install 'agent-framework-core>=1.15.0'`"
        ) from exc

    import openai as openai_sdk

    # Determine model string and API key.
    if spec.provider is ModelProvider.OPENAI:
        model_id = spec.model
        api_key = settings.openai_api_key
        base_url = None
    elif spec.provider is ModelProvider.ANTHROPIC:
        # LiteLLM's OpenAI-compat proxy for Anthropic.
        model_id = f"anthropic/{spec.model}"
        api_key = settings.anthropic_api_key
        base_url = None  # litellm handles routing
    else:
        model_id = f"gemini/{spec.model}"
        api_key = settings.google_api_key
        base_url = None

    class _AgentMeshChatClient(BaseChatClient):
        """Thin wrapper: converts MS Agent Framework Message objects to
        openai-sdk dicts, calls the completion API, converts back."""

        def __init__(self) -> None:
            super().__init__()
            self._model = model_id
            self._temperature = spec.temperature
            self._max_tokens = spec.max_tokens

        async def _inner_get_response(
            self,
            *,
            messages: Sequence[Message],
            stream: bool,
            options: Mapping[str, Any],
            **kwargs: Any,
        ) -> Awaitable[ChatResponse] | Any:
            # Convert MS framework Messages to openai-style dicts.
            oai_messages = []
            for msg in messages:
                role = str(getattr(msg, "role", "user"))
                # The Message.text property concatenates all content parts.
                text = getattr(msg, "text", None) or ""
                if not text and hasattr(msg, "contents") and msg.contents:
                    text = " ".join(
                        str(c) for c in msg.contents if c
                    )
                oai_messages.append({"role": role, "content": text})

            # Use litellm for non-OpenAI providers, openai SDK for OpenAI.
            if spec.provider is not ModelProvider.OPENAI:
                import litellm
                response = await litellm.acompletion(
                    model=self._model,
                    messages=oai_messages,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                )
                reply_text = response.choices[0].message.content or ""
            else:
                client = openai_sdk.AsyncOpenAI(api_key=api_key)
                response = await client.chat.completions.create(
                    model=self._model,
                    messages=oai_messages,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                )
                reply_text = response.choices[0].message.content or ""

            reply_msg = Message(role="assistant", contents=[reply_text])
            return ChatResponse(messages=[reply_msg], model=self._model)

    return _AgentMeshChatClient()


class MSAgentFrameworkRuntime(AgentRuntime):
    framework = AgentFramework.MS_AGENT_FRAMEWORK
    display_name = "MS Agent Framework GroupChat"
    description = (
        "Microsoft Agent Framework with GroupChat orchestration — "
        "round-robin specialists refining a shared conversation."
    )

    def _spec(self, ctx: RunContext) -> ModelSpec:
        return ModelSpec(
            provider=ctx.provider, model=ctx.model,
            temperature=ctx.temperature, max_tokens=ctx.max_tokens,
        )

    def _build_agents(self, ctx: RunContext,
                      tool_context: dict[str, str]) -> list[Any]:
        """Instantiate MS Agent Framework Agent objects for each enabled
        specialist, with tool results pre-injected into instructions."""
        try:
            from agent_framework import Agent
        except ImportError as exc:
            raise FrameworkNotAvailableError(
                "agent-framework-core is not installed. "
                "`pip install 'agent-framework-core>=1.15.0'`"
            ) from exc

        spec = self._spec(ctx).validate()
        client = _build_chat_client(spec)
        enabled = {s.name for s in specs_for(ctx.enabled_agents)}
        memory_block = ctx.memory_block()

        agents: list[Any] = []
        for name in AGENT_ORDER:
            if name not in enabled:
                continue
            agent_spec = AGENT_SPECS[name]
            instruction_parts = [agent_spec.instruction]
            if memory_block:
                instruction_parts.append(memory_block)

            # Inject pre-fetched tool results as context.
            tc = tool_context.get(name)
            if tc:
                instruction_parts.append(
                    f"Pre-fetched evidence from your tools:\n{tc}"
                )

            # Inject other specialists' findings.
            for other_name in AGENT_ORDER:
                if other_name == name:
                    continue
                other_tc = tool_context.get(other_name)
                if other_tc:
                    display = AGENT_SPECS[other_name].display_name
                    instruction_parts.append(
                        f"{display}'s findings:\n{other_tc}"
                    )

            agents.append(
                Agent(
                    client=client,
                    name=agent_spec.display_name,
                    description=agent_spec.description,
                    instructions="\n\n".join(instruction_parts),
                )
            )

        if not agents:
            raise FrameworkNotAvailableError(
                "No specialists are enabled for this run."
            )

        return agents

    async def _pre_execute_tools(self, ctx: RunContext) -> dict[str, str]:
        """Run each specialist's tools before the group chat starts."""
        enabled = {s.name for s in specs_for(ctx.enabled_agents)}
        results: dict[str, str] = {}

        for name in AGENT_ORDER:
            if name not in enabled:
                continue
            spec = AGENT_SPECS[name]
            if not spec.tools:
                continue

            tool_outputs: list[str] = []
            for tool_name in spec.tools:
                fn = TOOL_REGISTRY.get(tool_name)
                if fn is None:
                    continue
                try:
                    output = await self._call_tool(tool_name, fn, ctx)
                    if output:
                        tool_outputs.append(
                            f"[{tool_name}]: {output[:2000]}"
                        )
                except Exception as exc:
                    log.warning("ms_agent_tool_prefetch_failed",
                                tool=tool_name, error=str(exc)[:200])
                    tool_outputs.append(
                        f"[{tool_name}]: (unavailable: "
                        f"{type(exc).__name__})"
                    )

            if tool_outputs:
                results[name] = "\n\n".join(tool_outputs)

        return results

    async def _call_tool(self, name: str, fn: Any,
                         ctx: RunContext) -> str:
        """Invoke a single tool with defaults from the user's message."""
        kwargs: dict[str, Any] = {}

        if name == "hybrid_search":
            kwargs = {"query": ctx.message, "top_k": 6}
        elif name == "web_search":
            kwargs = {"query": ctx.message, "max_results": 5}
        elif name == "corpus_overview":
            kwargs = {}
        elif name in ("fetch_document_chunk", "calculator",
                       "table_stats"):
            return ""
        elif name == "pii_scan":
            kwargs = {"text": ctx.message}
        elif name == "policy_lookup":
            kwargs = {"topic": ""}
        else:
            return ""

        result = await asyncio.wait_for(
            fn(**kwargs),
            timeout=settings.resilience.tool_timeout_seconds,
        )
        return result if isinstance(result, str) else json.dumps(result)

    async def stream(self, ctx: RunContext) -> AsyncIterator[AgentEvent]:
        tool_user_id.set(ctx.user_id)
        tool_document_ids.set(tuple(ctx.document_ids))
        run_id = str(ctx.run_id)

        yield AgentEvent(
            EventType.RUN_STARTED,
            {"framework": self.framework.value},
            agent="orchestrator", run_id=run_id,
        )

        try:
            try:
                from agent_framework.orchestrations import (
                    GroupChatBuilder,
                    GroupChatState,
                )
            except ImportError as exc:
                raise FrameworkNotAvailableError(
                    "agent-framework-orchestrations is not installed. "
                    "`pip install 'agent-framework-orchestrations>=1.1.0'`"
                ) from exc

            yield AgentEvent(
                EventType.PLAN,
                {"plan": [
                    "pre-fetch tool evidence for specialists",
                    "GroupChat round-robin: researcher -> retriever -> "
                    "analyst -> compliance -> writer",
                    "terminate on writer completion or max rounds",
                ]},
                agent="orchestrator", run_id=run_id,
            )

            tool_context = await self._pre_execute_tools(ctx)

            for agent_name, tc in tool_context.items():
                yield AgentEvent(
                    EventType.TOOL_RESULT,
                    {"tool": f"pre-fetch:{agent_name}",
                     "output": tc[:800]},
                    agent=agent_name, run_id=run_id,
                )

            agents = self._build_agents(ctx, tool_context)
            agent_names = [a.name for a in agents]

            def round_robin_selector(state: GroupChatState) -> str:
                return agent_names[
                    state.current_round % len(agent_names)
                ]

            def termination_condition(conversation: list[Any]) -> bool:
                """Stop when the Writer produces a final answer.

                The conversation list includes the initial user message at
                index 0, so assistant messages start from index 1.  We only
                check assistant messages for the Writer's output.
                """
                if not conversation:
                    return False
                last = conversation[-1]
                author = getattr(last, "author_name", None) or ""
                text = getattr(last, "text", "") or ""
                role = str(getattr(last, "role", ""))
                # Only check assistant messages (skip the initial user msg).
                if role != "assistant":
                    return False
                # Writer finishing without "REVISE" signals completion.
                if author == "Writer" and text and "REVISE" not in text.upper():
                    return True
                return False

            # max_rounds caps the total number of agent turns.  Two full
            # rotations through all specialists is generous.
            max_rounds = 2 * len(agents)

            workflow = GroupChatBuilder(
                participants=agents,
                termination_condition=termination_condition,
                selection_func=round_robin_selector,
                max_rounds=max_rounds,
                output_from="all",
            ).build()

            task = _render_task(ctx)

            for a in agents:
                yield AgentEvent(
                    EventType.AGENT_STARTED, {},
                    agent=a.name, run_id=run_id,
                )

            started = time.perf_counter()
            result = await workflow.run(task)
            elapsed_ms = int((time.perf_counter() - started) * 1000)

            final_text = ""
            citations: list[dict[str, Any]] = []
            seen_citations: set[tuple[Any, Any, Any]] = set()
            messages_emitted = 0
            last_text = ""

            for output in result.get_outputs():
                msgs = getattr(output, "messages", None)
                items = msgs if msgs is not None else [output]

                for msg in items:
                    author = (getattr(msg, "author_name", None)
                              or "assistant")
                    text = getattr(msg, "text", None)
                    if text is None:
                        text = str(msg)

                    # Skip the orchestrator's termination boilerplate.
                    if (author == "group_chat_orchestrator"
                            or "termination condition" in text.lower()):
                        continue

                    # Skip the echoed user message.
                    role = str(getattr(msg, "role", ""))
                    if role == "user":
                        continue

                    messages_emitted += 1
                    last_text = text

                    yield AgentEvent(
                        EventType.TOKEN, {"text": text},
                        agent=author, run_id=run_id,
                    )

                    for cite in _citations_from_text(text):
                        key = (cite.get("filename"), cite.get("page"),
                               cite.get("marker"))
                        if key not in seen_citations:
                            seen_citations.add(key)
                            citations.append(cite)

                    if author == "Writer":
                        final_text = text

                    yield AgentEvent(
                        EventType.AGENT_FINISHED,
                        {"summary": text[:500]},
                        agent=author, run_id=run_id,
                    )

            if not final_text and messages_emitted > 0:
                final_text = last_text

            if citations:
                yield AgentEvent(
                    EventType.CITATION, {"citations": citations},
                    agent="retriever", run_id=run_id,
                )

            yield AgentEvent(
                EventType.USAGE,
                {"messages": messages_emitted,
                 "elapsed_ms": elapsed_ms},
                agent="orchestrator", run_id=run_id,
            )

            if not final_text:
                yield AgentEvent(
                    EventType.ERROR,
                    {"message": "The group chat produced no answer.",
                     "code": "no_output"},
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
            yield AgentEvent(
                EventType.ERROR,
                {"message": exc.message, "code": exc.code},
                run_id=run_id,
            )
        except Exception as exc:
            log.exception("ms_agent_run_failed")
            yield AgentEvent(
                EventType.ERROR,
                {"message": f"{type(exc).__name__}: {exc}"[:600]},
                run_id=run_id,
            )


# ===================================================================
# Module-level helpers
# ===================================================================

def _render_task(ctx: RunContext) -> str:
    """Compose the group-chat task prompt from history + message."""
    parts: list[str] = []
    if ctx.history:
        lines: list[str] = []
        total = 0
        for turn in ctx.history[-HISTORY_TURNS:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if len(content) > PER_MESSAGE_CHAR_CAP:
                content = content[:PER_MESSAGE_CHAR_CAP] + "..."
            line = f"{role}: {content}"
            total += len(line)
            if total > HISTORY_CHAR_BUDGET:
                break
            lines.append(line)
        if lines:
            parts.append("Conversation so far:\n" + "\n".join(lines))
    parts.append(f"User request:\n{ctx.message}")
    return "\n\n".join(parts)


def _citations_from_text(text: str) -> list[dict[str, Any]]:
    return [
        {"filename": None, "page": None, "marker": m}
        for m in CITATION_RE.findall(text)
    ]
