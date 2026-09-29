"""Every MCP server, by key. `build(key)` returns its FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI

SERVERS = ["orders", "catalog", "documents", "policy_kb", "risk",
           "case_mgmt", "payments"]


def build(key: str) -> FastAPI:
    module = __import__(f"refundry.servers.{key}", fromlist=["mcp"])
    return module.mcp.app()
