"""The FastAPI backend.

    User  ->  FastAPI  ->  Arbiter  ->  six A2A peers  ->  MCP servers / functions

This is the ONLY process a person talks to, and the last in-process hop in the
whole system: everything past `client_for("arbiter")` is a network call that can
fail on its own.

What lives here and nowhere else:
  * authentication, rate limiting, and the correlation id every hop inherits
  * turning one HTTP request into one A2A task
  * SSE, so a browser can watch a case without polling

What does NOT live here: any refund logic at all. The gateway cannot decide
anything, and that is deliberate.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from refundry import ids, store
from refundry.a2a import A2AClient
from refundry.agents.registry import AGENTS
from refundry.config import a2a_url, card_url, mcp_url, settings
from refundry.jev import jev
from refundry.mcp import MCPClient
from refundry.servers import SERVERS

API = "/api/v1"


# --------------------------------------------------------------------------
# Request / response shapes
# --------------------------------------------------------------------------


class FileClaim(BaseModel):
    order_ref: str = Field(examples=["NW-7731094"])
    buyer_ref: str = Field(default="BUY-90211")
    narrative: str = Field(examples=[
        "It arrived with the boiler casing cracked. The seller is telling me "
        "to pay return shipping on a machine that showed up broken."])
    evidence_refs: list[str] = Field(default_factory=list)


class Approval(BaseModel):
    approved: bool = True
    approver: str = Field(default="", examples=["elena.marchetti@northwind"])
    note: str = ""


# --------------------------------------------------------------------------
# Middleware
# --------------------------------------------------------------------------


class RateLimiter:
    """Crude fixed-window limiter. Real deployments use the gateway's own."""

    def __init__(self, limit: int = 120, window: float = 60.0):
        self.limit, self.window = limit, window
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        seen = [t for t in self._hits.get(key, []) if now - t < self.window]
        seen.append(now)
        self._hits[key] = seen
        return len(seen) <= self.limit


def build() -> FastAPI:
    api = FastAPI(
        title="Refundry",
        version="1.0.0",
        description="A refund resolution network built on MCP and A2A, with a "
                    "System One model in the routing path.",
    )
    api.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])
    limiter = RateLimiter()

    @api.middleware("http")
    async def correlate(request: Request, call_next):
        """Mint the correlation id here. Every hop below inherits it."""
        trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex[:16]
        request.state.trace_id = trace_id
        if not limiter.allow(request.client.host if request.client else "anon"):
            raise HTTPException(429, "rate limit exceeded")
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        response.headers["x-elapsed-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        return response

    arbiter = lambda: A2AClient(a2a_url("arbiter"), name="arbiter",
                                caller="gateway", timeout=180)

    # ---------------------------------------------------------------- claims

    @api.post(f"{API}/refunds", tags=["refunds"])
    async def file_claim(claim: FileClaim, request: Request):
        """File a refund claim. Returns the case, and the A2A task it became.

        The response is not always a result. If the amount needs a signature the
        task comes back as `input-required`, which is a legitimate outcome.
        """
        case_id = ids.case_id(claim.order_ref)
        context_id = ids.context_id(case_id)
        store.audit("gateway", "claim.filed", target=case_id,
                    context_id=context_id, trace_id=request.state.trace_id,
                    detail=claim.narrative[:200])

        task = await arbiter().send(
            claim.model_dump(), context_id=context_id,
            text=f"refund claim on {claim.order_ref}")

        return _view(task, case_id, context_id)

    @api.get(f"{API}/refunds/{{case_id}}", tags=["refunds"])
    async def get_case(case_id: str):
        record = store.load_case(case_id)
        if record is None:
            raise HTTPException(404, f"no case {case_id}")
        return {"case_id": case_id, "record": record,
                "notes": store.notes(case_id),
                "tasks": store.tasks_for_context(ids.context_id(case_id))}

    @api.post(f"{API}/refunds/{{case_id}}/approve", tags=["refunds"])
    async def approve(case_id: str, approval: Approval, request: Request):
        """Answer the question the task asked.

        The approval is a message on the SAME task id, not a new call. That is
        what lets the graph resume at the node it stopped on.
        """
        context_id = ids.context_id(case_id)
        waiting = [t for t in store.tasks_for_context(context_id)
                   if t.get("agent") == "arbiter"
                   and t["status"]["state"] == "input-required"]
        if not waiting:
            raise HTTPException(409, f"no task on {case_id} is waiting for input")
        if approval.approved and not approval.approver:
            raise HTTPException(422, "an approval needs a named approver (MKT-060)")

        task_id = waiting[-1]["id"]
        store.audit("gateway", "approval.submitted", target=case_id,
                    context_id=context_id, trace_id=request.state.trace_id,
                    detail={"approver": approval.approver,
                            "approved": approval.approved})

        task = await arbiter().send(
            approval.model_dump(), context_id=context_id,
            text=f"approval for {case_id}", task_id=task_id)
        return _view(task, case_id, context_id)

    @api.get(f"{API}/refunds/{{case_id}}/stream", tags=["refunds"])
    async def stream(case_id: str):
        """Server-sent events: the case's own audit trail, as it is written."""
        context_id = ids.context_id(case_id)

        async def gen():
            seen = 0
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                rows = store.trail(context_id)
                for row in rows[seen:]:
                    yield f"event: trail\ndata: {json.dumps(row, default=str)}\n\n"
                seen = len(rows)
                record = store.load_case(case_id)
                if record and record.get("status") in ("resolved", "declined"):
                    yield f"event: done\ndata: {json.dumps(record, default=str)}\n\n"
                    return
                await asyncio.sleep(0.25)
            yield "event: timeout\ndata: {}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    # ----------------------------------------------------------------- cases

    @api.get(f"{API}/cases", tags=["cases"])
    async def cases():
        return {"cases": store.list_cases()}

    @api.get(f"{API}/trail/{{case_id}}", tags=["cases"])
    async def trail(case_id: str):
        """Every A2A exchange and MCP call for one case, in order."""
        return {"case_id": case_id,
                "trail": store.trail(ids.context_id(case_id))}

    @api.get(f"{API}/ledger", tags=["cases"])
    async def ledger():
        return {"ledger": store.ledger()}

    # ------------------------------------------------------------- discovery

    @api.get(f"{API}/agents", tags=["discovery"])
    async def agents():
        """Fetch every Agent Card. This is discovery, and in a real estate it
        is an allow-list rather than the open internet."""
        import httpx

        out = []
        async with httpx.AsyncClient(timeout=5) as http:
            for key in AGENTS:
                try:
                    r = await http.get(card_url(key))
                    card = r.json()
                    out.append({"key": key, "reachable": True,
                                "name": card["name"],
                                "organization": card["provider"]["organization"],
                                "version": card["version"],
                                "skills": [s["id"] for s in card["skills"]],
                                "signature": card.get("signature", {}).get("kid")})
                except Exception as exc:
                    out.append({"key": key, "reachable": False, "error": str(exc)})
        return {"agents": out}

    @api.get(f"{API}/servers", tags=["discovery"])
    async def servers():
        """Every MCP server, with its scope and risk tier."""
        out = []
        for key in SERVERS:
            try:
                info = await MCPClient(mcp_url(key), name=key).discover()
                out.append({"key": key, "reachable": True, **info["serverInfo"],
                            "stateless": info.get("stateless")})
            except Exception as exc:
                out.append({"key": key, "reachable": False, "error": str(exc)})
        return {"servers": out}

    # ----------------------------------------------------------------- ops

    @api.get("/health", tags=["ops"])
    @api.get(f"{API}/health", tags=["ops"])
    async def health():
        return {"service": "refundry-gateway", "ok": True,
                "reasoning": settings.reasoning,
                "jev_backend": jev.backend,
                "auto_approval_limit": settings.auto_approval_limit,
                "confidence_floor": settings.confidence_floor}

    @api.get(f"{API}/doctor", tags=["ops"])
    async def doctor():
        """Check every process separately, so you learn which piece is unhappy
        before reading any logs."""
        import httpx

        checks = []
        async with httpx.AsyncClient(timeout=3) as http:
            for key in AGENTS:
                try:
                    r = await http.get(card_url(key))
                    checks.append({"kind": "agent", "key": key,
                                   "ok": r.status_code == 200})
                except Exception as exc:
                    checks.append({"kind": "agent", "key": key, "ok": False,
                                   "error": type(exc).__name__})
        for key in SERVERS:
            try:
                await MCPClient(mcp_url(key), name=key, timeout=3).discover()
                checks.append({"kind": "mcp", "key": key, "ok": True})
            except Exception as exc:
                checks.append({"kind": "mcp", "key": key, "ok": False,
                               "error": type(exc).__name__})
        healthy = all(c["ok"] for c in checks)
        return {"ok": healthy, "jev_backend": jev.backend, "checks": checks}

    return api


def _view(task: dict, case_id: str, context_id: str) -> dict:
    """One shape for every claim response."""
    state = task["status"]["state"]
    case = A2AClient.result(task, "case")
    approval = A2AClient.result(task, "approval_request")
    return {
        "case_id": case_id,
        "context_id": context_id,
        "task_id": task["id"],
        "task_state": state,
        "message": A2AClient.say(task),
        "awaiting_approval": state == "input-required",
        "approval_request": approval or None,
        "status": case.get("status") if case else None,
        "claim_type": case.get("claim_type") if case else None,
        "routing": case.get("routing") if case else {},
        "result": case.get("result") if case else None,
        "timeline": case.get("timeline") if case else [],
    }


app = build()
