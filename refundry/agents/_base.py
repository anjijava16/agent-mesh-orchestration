"""Shared agent scaffolding: MCP wiring, and the reason-or-degrade wrapper."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from refundry import store
from refundry.config import mcp_url, settings
from refundry.mcp import MCPClient


def client(server: str, *, caller: str, claims: dict[str, str] | None = None,
           timeout: float | None = None) -> MCPClient:
    """One client per server connection. The token and claims belong to the
    connection, which is where least privilege starts."""
    return MCPClient(
        mcp_url(server),
        name=f"{caller}->{server}",
        token=f"svc-{caller}-{server}",
        claims=claims,
        timeout=timeout,
    )


async def judge(agent: str, fn: Callable[[], Any], *, fallback: Any,
                context_id: str = "") -> Any:
    """Run the model half of an agent, and never let it take the network down.

    A timeout, a rate limit, a missing key or an unparseable answer degrades to
    the deterministic path -- and the degradation is visible in the trail, which
    matters more than the degradation itself.
    """
    if settings.deterministic:
        return fallback
    try:
        value = fn()
        if hasattr(value, "__await__"):
            value = await value
        return value if value else fallback
    except Exception as exc:  # pragma: no cover - the whole point is not raising
        traceback.print_exc()
        store.audit(agent, "reasoning.degraded", detail=f"{type(exc).__name__}: {exc}",
                    context_id=context_id)
        return fallback
