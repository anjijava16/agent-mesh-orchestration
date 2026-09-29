"""A minimal MCP server over streamable HTTP, on FastAPI.

Written against the wire format rather than wrapped in an SDK, because MCP is a
small protocol and seeing it unwrapped is worth more than seeing it hidden.

Follows the 2026-07-28 revision in the one way that matters operationally:
**it is stateless**. There is no initialize handshake to complete and no
Mcp-Session-Id to keep, so any replica behind a load balancer can serve any
request. `initialize` is still answered, for clients that send it.

Methods: initialize, server/discover, tools/list, tools/call,
resources/list, resources/read, ping.
"""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

PROTOCOL_VERSION = "2026-07-28"

# JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class ToolError(Exception):
    """Raised by a tool to return an error the model can act on.

    The message is what the model reads, so write it for the model:
    "order_ref NW-7731094 has no fulfilment record yet; carrier data lags by
    up to 4h" beats a stack trace.
    """

    def __init__(self, message: str, *, retryable: bool = False, hint: str = ""):
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.hint = hint

    def payload(self) -> dict:
        return {"error": self.message, "retryable": self.retryable,
                **({"hint": self.hint} if self.hint else {})}


_PY_TO_JSON = {str: "string", int: "integer", float: "number", bool: "boolean",
               list: "array", dict: "object"}


def _schema_for(fn: Callable) -> dict:
    """Derive an input schema from the signature. Good enough, and it cannot
    drift from the function the way a hand-written one does."""
    props: dict[str, Any] = {}
    required: list[str] = []
    sig = inspect.signature(fn)
    for name, param in sig.parameters.items():
        if name in ("self", "ctx"):
            continue
        ann = param.annotation
        origin = getattr(ann, "__origin__", None)
        if origin is list:
            props[name] = {"type": "array", "items": {"type": "string"}}
        else:
            props[name] = {"type": _PY_TO_JSON.get(ann, "string")}
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            props[name]["default"] = param.default
    return {"type": "object", "properties": props, "required": required}


@dataclass
class Tool:
    name: str
    fn: Callable
    description: str
    annotations: dict = field(default_factory=dict)
    input_schema: dict = field(default_factory=dict)

    def describe(self) -> dict:
        return {"name": self.name, "description": self.description,
                "inputSchema": self.input_schema, "annotations": self.annotations}


@dataclass
class Resource:
    uri: str
    fn: Callable
    name: str
    mime_type: str = "text/plain"

    def describe(self) -> dict:
        return {"uri": self.uri, "name": self.name, "mimeType": self.mime_type}


class MCPServer:
    """Collects tools and resources, then mounts them as a FastAPI app."""

    def __init__(self, name: str, *, scope: str, risk: str = "low",
                 version: str = "1.0.0"):
        self.name = name
        self.scope = scope
        self.risk = risk
        self.version = version
        self.tools: dict[str, Tool] = {}
        self.resources: dict[str, Resource] = {}

    # -- registration ------------------------------------------------------

    def tool(self, *, read_only: bool = False, destructive: bool = False,
             requires: list[str] | None = None):
        def deco(fn: Callable) -> Callable:
            ann = {"readOnlyHint": read_only, "destructiveHint": destructive}
            if requires:
                ann["requiresClaims"] = requires
            self.tools[fn.__name__] = Tool(
                name=fn.__name__,
                fn=fn,
                description=inspect.getdoc(fn) or "",
                annotations=ann,
                input_schema=_schema_for(fn),
            )
            return fn

        return deco

    def resource(self, uri: str, *, name: str = "", mime_type: str = "text/plain"):
        def deco(fn: Callable) -> Callable:
            self.resources[uri] = Resource(uri, fn, name or uri, mime_type)
            return fn

        return deco

    # -- dispatch ----------------------------------------------------------

    async def _call_tool(self, name: str, args: dict) -> dict:
        tool = self.tools.get(name)
        if tool is None:
            raise ToolError(
                f"no tool named {name!r} on the {self.name} server; "
                f"available: {', '.join(sorted(self.tools))}"
            )
        result = tool.fn(**args)
        if inspect.isawaitable(result):
            result = await result
        return result

    async def handle(self, msg: dict, headers: dict) -> dict | None:
        """One JSON-RPC message in, one response out (None for notifications)."""
        mid = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params") or {}

        def ok(result: Any) -> dict:
            return {"jsonrpc": "2.0", "id": mid, "result": result}

        def err(code: int, message: str, data: Any = None) -> dict:
            e = {"code": code, "message": message}
            if data is not None:
                e["data"] = data
            return {"jsonrpc": "2.0", "id": mid, "error": e}

        if method.startswith("notifications/"):
            return None

        if method == "initialize":
            return ok({
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": self.name, "version": self.version},
                "instructions": f"The {self.name} server. "
                                f"Scope {self.scope}, risk tier {self.risk}.",
            })

        if method == "server/discover":
            # 2026-07-28: identity and capability in one call, no session to close.
            return ok({
                "supportedVersions": [PROTOCOL_VERSION, "2025-06-18"],
                "capabilities": {"tools": {"listChanged": False},
                                 "resources": {"listChanged": False}},
                "serverInfo": {"name": self.name, "version": self.version,
                               "scope": self.scope, "riskTier": self.risk},
                "stateless": True,
            })

        if method == "ping":
            return ok({})

        if method == "tools/list":
            return ok({"tools": [t.describe() for t in self.tools.values()]})

        if method == "resources/list":
            return ok({"resources": [r.describe() for r in self.resources.values()]})

        if method == "resources/read":
            uri = params.get("uri", "")
            res = self.resources.get(uri)
            if res is None:
                return err(INVALID_PARAMS, f"no resource at {uri!r}")
            body = res.fn()
            if inspect.isawaitable(body):
                body = await body
            return ok({"contents": [{"uri": uri, "mimeType": res.mime_type,
                                     "text": body}]})

        if method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            tool = self.tools.get(name)
            if tool is not None:
                needed = tool.annotations.get("requiresClaims") or []
                missing = [c for c in needed if not headers.get(f"x-{c}")]
                if missing:
                    # A multi-round-trip style answer: say exactly what is missing
                    # rather than failing and making the caller guess.
                    return ok({
                        "isError": True,
                        "content": [{
                            "type": "text",
                            "text": f"{name} requires "
                                    f"{', '.join(missing)}; none supplied"}],
                        "structuredContent": {"error": "missing_claim",
                                              "missing": missing},
                    })
            try:
                value = await self._call_tool(name, args)
            except ToolError as exc:
                return ok({"isError": True,
                           "content": [{"type": "text", "text": exc.message}],
                           "structuredContent": exc.payload()})
            except TypeError as exc:
                return ok({
                    "isError": True,
                    "content": [{"type": "text",
                                 "text": f"bad arguments for {name}: {exc}"}],
                    "structuredContent": {"error": str(exc)}})
            return ok({
                "isError": False,
                "content": [{"type": "text", "text": json.dumps(value, default=str)}],
                "structuredContent": value,
            })

        return err(METHOD_NOT_FOUND, f"unknown method {method!r}")

    # -- app ---------------------------------------------------------------

    def app(self) -> FastAPI:
        api = FastAPI(title=f"MCP · {self.name}", version=self.version)
        router = APIRouter()

        @router.post("/mcp")
        async def mcp_endpoint(request: Request):
            try:
                body = await request.json()
            except Exception:
                return JSONResponse({"jsonrpc": "2.0", "id": None,
                                     "error": {"code": PARSE_ERROR,
                                               "message": "invalid JSON"}},
                                    status_code=400)
            headers = {k.lower(): v for k, v in request.headers.items()}
            if isinstance(body, list):  # batch
                out = [r for r in
                       [await self.handle(m, headers) for m in body] if r is not None]
                return JSONResponse(out)
            result = await self.handle(body, headers)
            if result is None:
                return JSONResponse(None, status_code=202)
            return JSONResponse(result)

        @router.get("/health")
        async def health():
            return {"server": self.name, "scope": self.scope, "risk": self.risk,
                    "protocol": PROTOCOL_VERSION, "tools": sorted(self.tools),
                    "resources": sorted(self.resources), "stateless": True,
                    "at": time.time()}

        api.include_router(router)
        return api
