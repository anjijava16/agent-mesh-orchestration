"""An MCP client written directly against the wire format.

About 120 lines of httpx. It exists for a practical reason and a pedagogical
one. The practical reason is that shared code cannot depend on whichever
version of the `mcp` package a given agent's framework happens to pin. The
pedagogical one is that the protocol is small:

    POST initialize                      (optional since 2026-07-28)
    POST notifications/initialized       (optional)
    POST tools/call                      for as long as you like

Per-client circuit breaker and timeout, because a retry storm in the agent tier
must never reach the order ledger.
"""

from __future__ import annotations

import itertools
import time
from typing import Any

import httpx

from refundry.config import settings


class MCPCallError(RuntimeError):
    """A tool returned isError, or the transport failed."""

    def __init__(self, message: str, *, structured: dict | None = None):
        super().__init__(message)
        self.structured = structured or {}


class Breaker:
    """Open after `threshold` consecutive failures; half-open after `cooldown`."""

    def __init__(self, threshold: int = 4, cooldown: float = 10.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self.failures = 0
        self.opened_at = 0.0

    @property
    def open(self) -> bool:
        if self.failures < self.threshold:
            return False
        if time.monotonic() - self.opened_at > self.cooldown:
            self.failures = self.threshold - 1  # half-open: allow one through
            return False
        return True

    def ok(self) -> None:
        self.failures = 0

    def fail(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()


class MCPClient:
    """One client per server connection, which is where least privilege starts:
    the auth header and the scope belong to the connection, not the agent."""

    def __init__(self, url: str, *, name: str = "", token: str = "",
                 claims: dict[str, str] | None = None, timeout: float | None = None):
        self.url = url
        self.name = name or url
        self.timeout = timeout or settings.mcp_timeout
        self._ids = itertools.count(1)
        self._breaker = Breaker()
        self._headers = {"content-type": "application/json",
                         "accept": "application/json, text/event-stream"}
        if token:
            self._headers["authorization"] = f"Bearer {token}"
        for key, value in (claims or {}).items():
            self._headers[f"x-{key}"] = value

    async def _rpc(self, method: str, params: dict | None = None) -> Any:
        if self._breaker.open:
            raise MCPCallError(
                f"{self.name} circuit breaker is open; not sending {method}")
        body = {"jsonrpc": "2.0", "id": next(self._ids), "method": method,
                "params": params or {}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                resp = await http.post(self.url, json=body, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            self._breaker.fail()
            raise MCPCallError(f"{self.name}: {type(exc).__name__}: {exc}") from exc
        self._breaker.ok()
        if isinstance(data, dict) and data.get("error"):
            raise MCPCallError(f"{self.name}: {data['error'].get('message')}")
        return data.get("result") if isinstance(data, dict) else data

    # -- protocol ----------------------------------------------------------

    async def discover(self) -> dict:
        return await self._rpc("server/discover")

    async def list_tools(self) -> list[dict]:
        return (await self._rpc("tools/list")).get("tools", [])

    async def list_resources(self) -> list[dict]:
        return (await self._rpc("resources/list")).get("resources", [])

    async def read_resource(self, uri: str) -> str:
        result = await self._rpc("resources/read", {"uri": uri})
        contents = result.get("contents") or [{}]
        return contents[0].get("text", "")

    async def call(self, tool: str, **arguments: Any) -> Any:
        result = await self._rpc("tools/call", {"name": tool, "arguments": arguments})
        if result.get("isError"):
            text = (result.get("content") or [{}])[0].get("text", "tool error")
            raise MCPCallError(f"{self.name}.{tool}: {text}",
                               structured=result.get("structuredContent"))
        return result.get("structuredContent")
