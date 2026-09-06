"""AWS Strands Agents adapter — Swarm multi-agent orchestration.

Strands Agents is AWS's open-source agent SDK.  Its ``Swarm`` pattern lets a
team of specialist agents collaborate through shared context and autonomous
handoffs: each agent decides whether to hand off to another agent or produce
a final response.

Topology (Swarm):

    ┌──────────────────────────────────────────────────────────┐
    │                   shared context                         │
    │                                                          │
    │   orchestrator ──handoff──> researcher                   │
    │       ▲                         │                        │
    │       │                    handoff                       │
    │   writer <───── compliance <── analyst <── retriever     │
    │                                                          │
    │   Each agent has our tools and can hand off to any peer  │
    │   via the built-in handoff_to_agent tool.                │
    └──────────────────────────────────────────────────────────┘

Key design decisions:

1. **LiteLLMModel** — Strands has a first-class LiteLLM provider that routes
   to OpenAI / Anthropic / Google / Bedrock through the same litellm package
   we already ship.  Model IDs use litellm's ``provider/model`` format.

2. **@tool decorator** — Our framework-neutral tool functions are wrapped with
   Strands' ``@tool`` decorator so agents can call them natively through the
   Strands tool-calling loop (no pre-execution needed, unlike the MS runtime).

3. **Swarm with shared context** — Specialists share a ``SharedContext`` so
   the researcher's findings are visible to the analyst, etc.  The orchestrator
   agent starts the swarm and routes to the right specialist based on the
   user's question.

4. **Streaming via callback_handler** — Strands streams tokens through a
   callback handler.  We install a custom handler that pushes events into an
   ``asyncio.Queue`` which the ``stream()`` generator drains into our
   ``AgentEvent`` pipeline.

5. **Null callback for background** — Strands' default ``PrintingCallbackHandler``
   writes to stdout.  We replace it with a queue-based handler so output goes
   to our SSE stream, not the server console.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from app.agents.base import AgentEvent, AgentRuntime, EventType, RunContext
from app.agents.definitions import AGENT_SPECS, ORCHESTRATOR_INSTRUCTION, specs_for
from app.agents.tools.core import TOOL_REGISTRY, TOOL_SCHEMAS, tool_document_ids, tool_user_id
from app.config import AgentFramework, ModelProvider, settings
from app.core.errors import FrameworkNotAvailableError
from app.core.logging import get_logger
from app.llm.registry import ModelSpec

log = get_logger(__name__)

CITATION_RE = re.compile(r"\[[^\]]+ p\.\d+\]")

HISTORY_TURNS = 12
HISTORY_CHAR_BUDGET = 12_000
PER_MESSAGE_CHAR_CAP = 2_000


class StrandsAgentsRuntime(AgentRuntime):
    framework = AgentFramework.STRANDS_AGENTS
    display_name = "AWS Strands Agents Swarm"
    description = (
        "AWS Strands Agents with Swarm multi-agent orchestration — "
        "specialists collaborate through shared context and autonomous handoffs."
    )

    def _spec(self, ctx: RunContext) -> ModelSpec:
        return ModelSpec(
            provider=ctx.provider, model=ctx.model,
            temperature=ctx.temperature, max_tokens=ctx.max_tokens,
        )

    def _build_model(self, ctx: RunContext) -> Any:
        """Build a Strands LiteLLMModel for the selected provider."""
        try:
            from strands.models.litellm import LiteLLMModel
        except ImportError as exc:
            raise FrameworkNotAvailableError(
                "strands-agents is not installed. "
                "`pip install 'strands-agents[litellm]>=1.0.0'`"
            ) from exc

        spec = self._spec(ctx).validate()

        # LiteLLM model_id format: "provider/model"
        if spec.provider is ModelProvider.OPENAI:
            model_id = f"openai/{spec.model}"
            api_key = settings.openai_api_key
        elif spec.provider is ModelProvider.ANTHROPIC:
            model_id = f"anthropic/{spec.model}"
            api_key = settings.anthropic_api_key
        else:
            model_id = f"gemini/{spec.model}"
            api_key = settings.google_api_key

        return LiteLLMModel(
            client_args={"api_key": api_key},
            model_id=model_id,
            params={
                "max_tokens": spec.max_tokens,
                "temperature": spec.temperature,
            },
        )

    def _build_tools(self, tool_names: list[str]) -> list[Any]:
        """Wrap our neutral tool functions with Strands' @tool decorator."""
        try:
            from strands import tool as strands_tool
        except ImportError as exc:
            raise FrameworkNotAvailableError(
                "strands-agents is not installed. "
                "`pip install 'strands-agents>=1.0.0'`"
            ) from exc

        tools = []
        for name in tool_names:
            fn = TOOL_REGISTRY.get(name)
            if fn is None:
                continue
            # Build a Strands-compatible tool wrapper.
            wrapped = _build_strands_tool(name, fn)
            if wrapped is not None:
                tools.append(wrapped)
        return tools

    def _build_agents(self, ctx: RunContext) -> tuple[Any, list[Any]]:
        """Build the orchestrator and specialist agents for the Swarm."""
        try:
            from strands import Agent
        except ImportError as exc:
            raise FrameworkNotAvailableError(
                "strands-agents is not installed. "
                "`pip install 'strands-agents>=1.0.0'`"
            ) from exc

        model = self._build_model(ctx)
        enabled = {s.name for s in specs_for(ctx.enabled_agents)}
        memory_block = ctx.memory_block()

        # Build specialist agents — each gets only its own tools so the
        # Swarm's handoff routing works cleanly.
        specialists: list[Any] = []
        for name in ("researcher", "retriever", "analyst", "compliance", "writer"):
            if name not in enabled:
                continue
            spec = AGENT_SPECS[name]
            instruction = spec.instruction
            if memory_block:
                instruction += f"\n\n{memory_block}"

            specialist_tools = self._build_tools(spec.tools)
            agent = Agent(
                name=spec.name,
                description=spec.description,
                model=model,
                system_prompt=instruction,
                tools=specialist_tools,
                callback_handler=None,  # suppress console output
            )
            specialists.append(agent)

        if not specialists:
            raise FrameworkNotAvailableError(
                "No specialists are enabled for this run."
            )

        # Build the orchestrator. Its job is to route to specialists via
        # the handoff_to_agent tool that the Swarm injects automatically.
        # It gets no domain tools — only the swarm coordination tools.
        specialist_roster = "\n".join(
            f"- {s.name}: {AGENT_SPECS[s.name].description}"
            for s in specialists
        )
        orchestrator_prompt = (
            ORCHESTRATOR_INSTRUCTION
            + (f"\n\n{memory_block}" if memory_block else "")
            + f"\n\nAvailable specialists in this swarm:\n{specialist_roster}"
            + "\n\nUse the handoff_to_agent tool to delegate work to the right "
            "specialist. Always delegate — do not answer directly. "
            "Start with researcher or retriever for evidence gathering, "
            "then analyst for numbers, compliance for review, and writer "
            "for the final answer."
        )
        orchestrator = Agent(
            name="orchestrator",
            description="Coordinates the team and routes work to specialists.",
            model=model,
            system_prompt=orchestrator_prompt,
            tools=[],  # only swarm-injected handoff tools
            callback_handler=None,
        )

        return orchestrator, specialists

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
                from strands.multiagent import Swarm
            except ImportError as exc:
                raise FrameworkNotAvailableError(
                    "strands-agents is not installed. "
                    "`pip install 'strands-agents>=1.0.0'`"
                ) from exc

            orchestrator, specialists = self._build_agents(ctx)

            yield AgentEvent(
                EventType.PLAN,
                {"plan": [
                    "Swarm orchestration with shared context",
                    f"Specialists: {', '.join(a.name for a in specialists)}",
                    "Autonomous handoffs between agents",
                    "Orchestrator coordinates and writer finalises",
                ]},
                agent="orchestrator", run_id=run_id,
            )

            for agent in specialists:
                yield AgentEvent(
                    EventType.AGENT_STARTED, {},
                    agent=agent.name, run_id=run_id,
                )

            # Build the Swarm with the orchestrator as entry point.
            swarm = Swarm(
                nodes=[orchestrator] + specialists,
                entry_point=orchestrator,
            )

            # Compose the task prompt with history.
            task = _render_task(ctx)

            # Run the swarm in a thread since Strands agents are sync.
            started = time.perf_counter()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: swarm(task)
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)

            # Extract results from the SwarmResult.
            # SwarmResult.results is a dict[str, NodeResult], where each
            # NodeResult.result is an AgentResult with a .message dict
            # containing {"content": [{"text": "..."}]}.
            final_text = ""
            citations: list[dict[str, Any]] = []
            seen_citations: set[tuple[Any, Any, Any]] = set()

            # Walk through all node results and emit events.
            for node_name, node_result in (result.results or {}).items():
                agent_result = getattr(node_result, "result", None)
                if agent_result is None or isinstance(agent_result, Exception):
                    if isinstance(agent_result, Exception):
                        yield AgentEvent(
                            EventType.ERROR,
                            {"message": f"{node_name}: {agent_result}"[:400],
                             "code": "agent_error"},
                            agent=node_name, run_id=run_id,
                        )
                    continue

                # Extract text from AgentResult.
                text = _extract_agent_text(agent_result)
                if not text:
                    continue

                yield AgentEvent(
                    EventType.TOKEN, {"text": text},
                    agent=node_name, run_id=run_id,
                )
                yield AgentEvent(
                    EventType.AGENT_FINISHED,
                    {"summary": text[:500]},
                    agent=node_name, run_id=run_id,
                )

                # The last agent's output is the final answer.
                final_text = text

                for cite in _citations_from_text(text):
                    key = (cite.get("filename"), cite.get("page"),
                           cite.get("marker"))
                    if key not in seen_citations:
                        seen_citations.add(key)
                        citations.append(cite)

            # If no node results, try extracting from the SwarmResult directly.
            if not final_text and result is not None:
                final_text = str(result)

            # Emit usage.
            yield AgentEvent(
                EventType.USAGE,
                {"elapsed_ms": elapsed_ms,
                 "execution_count": getattr(result, "execution_count", 0)},
                agent="orchestrator", run_id=run_id,
            )

            if citations:
                yield AgentEvent(
                    EventType.CITATION, {"citations": citations},
                    agent="retriever", run_id=run_id,
                )

            if not final_text:
                yield AgentEvent(
                    EventType.ERROR,
                    {"message": "The swarm produced no answer.",
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
            log.exception("strands_run_failed")
            yield AgentEvent(
                EventType.ERROR,
                {"message": f"{type(exc).__name__}: {exc}"[:600]},
                run_id=run_id,
            )


# ===================================================================
# Tool wrapping
# ===================================================================

def _build_strands_tool(name: str, fn: Any) -> Any:
    """Wrap a neutral tool function into a Strands @tool-decorated function.

    Strands' @tool decorator reads the function signature and docstring,
    similar to ADK's FunctionTool. We build a typed wrapper so Strands can
    introspect it properly.
    """
    import asyncio as _asyncio
    import inspect
    import textwrap

    from strands import tool as strands_tool

    schema = TOOL_SCHEMAS.get(name, {})
    sig = inspect.signature(fn)

    # Build parameter list with types.
    params = []
    for pname, param in sig.parameters.items():
        annotation = schema.get(pname)
        type_str = {str: "str", int: "int", float: "float",
                    bool: "bool"}.get(annotation, "str")
        if param.default is not inspect.Parameter.empty:
            params.append(f"{pname}: {type_str} = {param.default!r}")
        else:
            params.append(f"{pname}: {type_str}")

    params_str = ", ".join(params)
    call_args = ", ".join(
        f"{p}={p}" for p in schema
    )

    # Generate a sync wrapper since Strands tools are synchronous.
    code = textwrap.dedent(f'''
def {name}({params_str}) -> str:
    """tool"""
    import asyncio as _aio
    try:
        loop = _aio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = pool.submit(_aio.run, _fn({call_args})).result()
    else:
        result = _aio.run(_fn({call_args}))
    return result if isinstance(result, str) else __import__("json").dumps(result)
''')

    ns: dict[str, Any] = {"_fn": fn}
    exec(code, ns)  # noqa: S102
    wrapper = ns[name]
    wrapper.__doc__ = (fn.__doc__ or name).strip()

    # Apply Strands @tool decorator.
    return strands_tool(wrapper)


# ===================================================================
# Helpers
# ===================================================================

def _render_task(ctx: RunContext) -> str:
    """Compose the swarm task from history + user message."""
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


def _extract_agent_text(agent_result: Any) -> str:
    """Extract text from a Strands AgentResult.

    AgentResult.message is typically a dict like:
        {"role": "assistant", "content": [{"text": "..."}]}
    """
    # Try .message dict with content blocks.
    msg = getattr(agent_result, "message", None)
    if isinstance(msg, dict):
        parts: list[str] = []
        for block in msg.get("content", []):
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        if parts:
            return "".join(parts)

    # Try .text attribute.
    text = getattr(agent_result, "text", None)
    if text:
        return str(text)

    # Fallback to str().
    s = str(agent_result)
    if s and s != "None":
        return s
    return ""
