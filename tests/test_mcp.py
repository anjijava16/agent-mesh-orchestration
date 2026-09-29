"""The MCP wire format, with no client library involved."""

import pytest
from fastapi.testclient import TestClient

from refundry.servers import SERVERS, build


def rpc(client, method, params=None, **headers):
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method,
                                     "params": params or {}}, headers=headers).json()


@pytest.mark.parametrize("key", SERVERS)
def test_every_server_discovers(key):
    """server/discover answers without an initialize handshake first.

    That is the 2026-07-28 stateless revision: no session to open, so any
    replica behind a load balancer can serve any request.
    """
    r = rpc(TestClient(build(key)), "server/discover")["result"]
    assert r["stateless"] is True
    assert r["serverInfo"]["name"] == key
    assert r["serverInfo"]["scope"]


@pytest.mark.parametrize("key", SERVERS)
def test_every_tool_has_a_description_and_a_schema(key):
    tools = rpc(TestClient(build(key)), "tools/list")["result"]["tools"]
    assert tools
    for t in tools:
        assert t["description"], f"{key}.{t['name']} has no docstring"
        assert t["inputSchema"]["type"] == "object"


def test_notifications_get_no_response():
    c = TestClient(build("orders"))
    r = c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert r.status_code == 202


def test_tool_errors_are_actionable_not_stack_traces():
    c = TestClient(build("orders"))
    out = rpc(c, "tools/call", {"name": "get_order",
                                "arguments": {"order_ref": "NOPE"}})["result"]
    assert out["isError"]
    text = out["content"][0]["text"]
    assert "NOPE" in text and "case record" in text
    assert "Traceback" not in text


def test_unknown_tool_lists_the_real_ones():
    c = TestClient(build("orders"))
    out = rpc(c, "tools/call", {"name": "get_ordr", "arguments": {}})["result"]
    assert out["isError"]
    assert "get_order" in out["content"][0]["text"]


def test_payments_refuses_without_the_idempotency_claim():
    """The claim is enforced by the MCP layer, before the tool body runs."""
    c = TestClient(build("payments"))
    out = rpc(c, "tools/call", {"name": "issue_refund", "arguments": {
        "case_id": "RFD-1", "amount": 10.0, "tender": "card",
        "idempotency_key": "whatever"}})["result"]
    assert out["isError"]
    assert out["structuredContent"]["error"] == "missing_claim"


def test_policy_resources_are_readable():
    c = TestClient(build("policy_kb"))
    uris = [r["uri"] for r in rpc(c, "resources/list")["result"]["resources"]]
    assert "policy://marketplace/MKT-014" in uris
    body = rpc(c, "resources/read",
               {"uri": "policy://marketplace/MKT-014"})["result"]["contents"][0]["text"]
    assert "overrides" in body
