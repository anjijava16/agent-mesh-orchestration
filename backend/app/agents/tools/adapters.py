"""Wrap the neutral tools into each framework's own tool type.

Every wrapper adds the same three things the raw function does not have:
a per-tool circuit breaker, a timeout, and a structured log line. That is why
these go through `_guard` rather than being passed straight through.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

from app.agents.tools.core import TOOL_REGISTRY, TOOL_SCHEMAS
from app.config import settings
from app.core.errors import CircuitOpenError
from app.core.logging import get_logger
from app.core.resilience import tool_breaker

log = get_logger(__name__)


def _guard(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
    breaker = tool_breaker(name)

    async def wrapped(**kwargs: Any) -> str:
        log.debug("tool_invoke", tool=name, input_keys=list(kwargs.keys()),
                  input_preview={k: str(v)[:200] for k, v in kwargs.items()})
        started = time.perf_counter()
        try:
            async def call() -> Any:
                return await asyncio.wait_for(fn(**kwargs), timeout=settings.resilience.tool_timeout_seconds)

            result = await breaker.call(call)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            result_str = result if isinstance(result, str) else json.dumps(result)
            log.info("tool_ok", tool=name, ms=elapsed_ms)
            log.debug("tool_result", tool=name, ms=elapsed_ms,
                      output_length=len(result_str),
                      output_preview=result_str[:500])
            return result_str
        except CircuitOpenError as exc:
            log.warning("tool_circuit_open", tool=name)
            return json.dumps({"error": str(exc), "recoverable": True})
        except TimeoutError:
            log.warning("tool_timeout", tool=name,
                        ms=int((time.perf_counter() - started) * 1000))
            return json.dumps({"error": f"Tool '{name}' timed out.", "recoverable": True})
        except Exception as exc:
            log.warning("tool_failed", tool=name, error=str(exc)[:300],
                        ms=int((time.perf_counter() - started) * 1000))
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"[:400], "recoverable": False})

    wrapped.__name__ = name
    wrapped.__doc__ = fn.__doc__
    return wrapped


# ---------------------------------------------------------------- LangChain
def langchain_tools(names: list[str]) -> list[Any]:
    """StructuredTool objects for LangGraph and DeepAgents."""
    from langchain_core.tools import StructuredTool

    out = []
    for name in names:
        fn = TOOL_REGISTRY.get(name)
        if fn is None:
            continue
        guarded = _guard(name, fn)

        # StructuredTool infers the schema from the *original* signature, so we
        # hand it the raw coroutine for typing and the guarded one for execution.
        async def _runner(_g=guarded, **kwargs: Any) -> str:
            return await _g(**kwargs)

        out.append(
            StructuredTool.from_function(
                coroutine=_runner,
                func=None,
                name=name,
                description=(fn.__doc__ or name).strip(),
                infer_schema=False,
                args_schema=_pydantic_schema(name),
            )
        )
    return out


def _pydantic_schema(name: str) -> Any:
    from pydantic import create_model

    fields: dict[str, Any] = {}
    for field_name, field_type in TOOL_SCHEMAS.get(name, {}).items():
        default = ... if field_name in ("query", "expression", "text", "document_id", "numbers") else None
        fields[field_name] = (field_type | None, default) if default is None else (field_type, default)
    return create_model(f"{name.title().replace('_', '')}Args", **fields)  # type: ignore[arg-type]


# --------------------------------------------------------------- Google ADK
def adk_tools(names: list[str]) -> list[Any]:
    """ADK FunctionTools. ADK reads the signature and docstring, so we rebuild a
    typed async shim per tool rather than passing **kwargs."""
    import inspect

    from google.adk.tools import FunctionTool

    # ADK 2.0 bug: internal modules use `from __future__ import annotations`
    # but get_type_hints() cannot resolve ToolContext in all contexts.
    # Patch it into the modules that need it.
    _patch_adk_toolcontext()

    out = []
    for name in names:
        fn = TOOL_REGISTRY.get(name)
        if fn is None:
            continue
        guarded = _guard(name, fn)
        schema = TOOL_SCHEMAS.get(name, {})

        shim = _build_adk_shim(name, fn, guarded, schema)
        out.append(FunctionTool(func=shim))
    return out


_adk_patched = False


def _patch_adk_toolcontext() -> None:
    """Inject ToolContext into ADK modules that fail get_type_hints()."""
    global _adk_patched
    if _adk_patched:
        return
    _adk_patched = True
    try:
        from google.adk.tools.tool_context import ToolContext
        import google.adk.tools.function_tool as ft_mod
        import google.adk.tools._function_tool_declarations as decl_mod
        import google.adk.tools._automatic_function_calling_util as afc_mod

        for mod in (ft_mod, decl_mod, afc_mod):
            if "ToolContext" not in vars(mod):
                setattr(mod, "ToolContext", ToolContext)
    except Exception:
        pass  # If ADK changes its internals, don't crash


def _build_adk_shim(
    name: str,
    original_fn: Any,
    guarded_fn: Any,
    schema: dict[str, Any],
) -> Any:
    """Create a typed async function that ADK can introspect safely.

    We generate code with an explicit signature so get_type_hints() never
    needs to resolve forward references from another module.
    """
    import inspect
    import textwrap

    sig = inspect.signature(original_fn)
    params = []
    for pname, param in sig.parameters.items():
        annotation = schema.get(pname)
        type_str = {str: "str", int: "int", float: "float", bool: "bool"}.get(annotation, "str")
        if param.default is not inspect.Parameter.empty:
            params.append(f"{pname}: {type_str} = {param.default!r}")
        else:
            params.append(f"{pname}: {type_str}")

    params_str = ", ".join(params)
    bind_args = ", ".join(f"{p}={p}" for p in schema)

    code = textwrap.dedent(f'''
async def {name}({params_str}) -> str:
    """tool"""
    import inspect as _ins
    _bound = _ins.signature(_orig).bind_partial({bind_args})
    _bound.apply_defaults()
    return await _guarded(**_bound.arguments)
''')

    ns: dict[str, Any] = {"_orig": original_fn, "_guarded": guarded_fn}
    exec(code, ns)  # noqa: S102
    func = ns[name]
    # Set the real docstring after exec to avoid quoting issues.
    func.__doc__ = (original_fn.__doc__ or name).strip()
    return func


# --------------------------------------------------- Claude Agent SDK (MCP)
def claude_sdk_server(names: list[str], server_name: str = "agentmesh") -> Any:
    """An in-process MCP server exposing our tools to the Claude Agent SDK.

    In-process means no subprocess and no IPC - the tool call lands directly in
    this event loop, which is what we want inside a FastAPI worker.
    """
    from claude_agent_sdk import create_sdk_mcp_server
    from claude_agent_sdk import tool as sdk_tool

    handlers = []
    for name in names:
        fn = TOOL_REGISTRY.get(name)
        if fn is None:
            continue
        guarded = _guard(name, fn)
        schema = dict(TOOL_SCHEMAS.get(name, {}))

        @sdk_tool(name, (fn.__doc__ or name).strip()[:400], schema)
        async def handler(args: dict[str, Any], _g=guarded) -> dict[str, Any]:
            text = await _g(**args)
            return {"content": [{"type": "text", "text": text}]}

        handlers.append(handler)

    return create_sdk_mcp_server(name=server_name, version="1.0.0", tools=handlers)
