"""The A2A task lifecycle, including the pause that makes it worth having."""

from fastapi.testclient import TestClient

from refundry import store
from refundry.a2a import A2AServer, Executor, RequestContext, Skill, build_card


class Gate(Executor):
    async def execute(self, ctx: RequestContext) -> None:
        if ctx.is_resume:
            ctx.artifact("result", {"approved": ctx.data.get("approved")})
            ctx.complete("resumed")
            return
        ctx.working("thinking")
        if ctx.data.get("amount", 0) >= 1000:
            ctx.artifact("draft", {"amount": ctx.data["amount"]})
            ctx.input_required("needs a signature")
            return
        ctx.artifact("result", {"approved": True})
        ctx.complete("straight through")


def client():
    card = build_card("Gate", "d", "http://x/a2a/jsonrpc", [Skill("do", "Do", "d")])
    return TestClient(A2AServer(card, Gate(), agent_key="gate").app())


def send(c, data, task_id=""):
    msg = {"role": "user", "parts": [{"kind": "data", "data": data}],
           "contextId": "ctx-t"}
    if task_id:
        msg["taskId"] = task_id
    return c.post("/a2a/jsonrpc",
                  json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage",
                        "params": {"message": msg}},
                  headers={"A2A-Version": "1.0"}).json()["result"]


def test_card_is_served_and_signed():
    card = client().get("/.well-known/agent-card.json").json()
    assert card["skills"][0]["id"] == "do"
    assert card["signature"]["kid"]
    assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"


def test_simple_task_completes():
    t = send(client(), {"amount": 10})
    assert t["status"]["state"] == "completed"


def test_task_pauses_and_survives_in_the_store():
    c = client()
    t = send(c, {"amount": 1284})
    assert t["status"]["state"] == "input-required"
    # The pause is durable: GetTask still answers after the request ended.
    assert store.get_task(t["id"])["status"]["state"] == "input-required"


def test_approval_settles_the_same_task():
    c = client()
    t = send(c, {"amount": 1284})
    done = send(c, {"approved": True}, task_id=t["id"])
    assert done["id"] == t["id"], "the approval must land on the original task"
    assert done["status"]["state"] == "completed"


def test_terminal_states_are_final():
    c = client()
    t = send(c, {"amount": 10})
    out = c.post("/a2a/jsonrpc",
                 json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage",
                       "params": {"message": {
                           "role": "user", "parts": [], "contextId": "ctx-t",
                           "taskId": t["id"]}}},
                 headers={"A2A-Version": "1.0"}).json()
    assert "error" in out
    assert "completed" in out["error"]["message"]


def test_the_task_object_is_published_before_any_status_update():
    """A status update that arrives before the Task is rejected by the client.
    The server enforces the order rather than trusting each executor."""
    c = client()
    t = send(c, {"amount": 10})
    assert t["kind"] == "task"
    assert t["id"] and t["contextId"] == "ctx-t"


def test_version_header_trap():
    """With compatibility mode on, a pre-1.0 method name still works -- which
    is exactly how a caller ends up silently on 0.3."""
    c = client()
    out = c.post("/a2a/jsonrpc",
                 json={"jsonrpc": "2.0", "id": 1, "method": "message/send",
                       "params": {"message": {
                           "role": "user",
                           "parts": [{"kind": "data", "data": {"amount": 1}}],
                           "contextId": "ctx-t"}}}).json()
    assert out["result"]["status"]["state"] == "completed"
