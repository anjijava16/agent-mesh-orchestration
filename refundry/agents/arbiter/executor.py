"""The Arbiter's A2A lifecycle.

This agent is a server and a client at the same time. It accepts a task from a
buyer, delegates over A2A to six peers, and forwards a pause from one of them
onto its own task -- without any node in the chain special-casing approvals.
"""

from __future__ import annotations

from fastapi import FastAPI

from refundry import ids, store
from refundry.a2a import A2AServer, Executor, RequestContext
from refundry.agents.arbiter.card import CARD
from refundry.agents.arbiter.graph import graph
from refundry.agents.arbiter.graph_engine import RunResult
from refundry.models import CaseState, Claim


def _state_from(data: dict) -> CaseState:
    claim = Claim(
        order_ref=data["order_ref"],
        buyer_ref=data.get("buyer_ref", ""),
        narrative=data.get("narrative", ""),
        evidence_refs=data.get("evidence_refs") or [],
    )
    case_id = data.get("case_id") or ids.case_id(claim.order_ref)
    return CaseState(case_id=case_id, context_id=ids.context_id(case_id), claim=claim)


def _publish(ctx: RequestContext, run: RunResult) -> None:
    state: CaseState = run.state
    ctx.artifact("case", state.model_dump(mode="json"))
    if run.status == "input-required":
        ctx.artifact("approval_request", run.payload or {},
                     text=(run.payload or {}).get("question", "approval needed"))
        ctx.input_required((run.payload or {}).get("question", "approval needed"))
        return

    if state.result and state.result.status == "posted":
        ctx.complete(f"{state.case_id}: {state.result.message}")
    elif state.status == "declined":
        ctx.complete(f"{state.case_id}: declined. "
                     f"{state.result.message if state.result else ''}".strip())
    else:
        ctx.complete(f"{state.case_id}: {state.status}")


class ArbiterExecutor(Executor):
    skill = "resolve_refund"

    async def execute(self, ctx: RequestContext) -> None:
        data = ctx.data

        # --- resume: an approval arrived on a task that was waiting
        if ctx.is_resume:
            saved = store.load_checkpoint(ctx.task_id)
            if saved is None:
                ctx.fail("no checkpoint for this task; cannot resume")
                return
            node, raw = saved
            state = CaseState(**raw)
            ctx.working(f"resuming at {node}")
            run = await graph.run(state, thread_id=ctx.task_id, start=node,
                                  resume={"approved": bool(data.get("approved")),
                                          "approver": data.get("approver", ""),
                                          "note": data.get("note", "")})
            store.audit("arbiter", "graph.resumed", context_id=state.context_id,
                        detail={"from": node, "visited": run.visited})
            _publish(ctx, run)
            return

        # --- first pass
        if not data.get("order_ref"):
            ctx.reject("resolve_refund needs an order_ref")
            return

        state = _state_from(data)
        # The task and the case share one contextId, so five processes produce
        # one ordered story.
        ctx.task["contextId"] = state.context_id
        ctx.working(f"opening {state.case_id}")

        run = await graph.run(state, thread_id=ctx.task_id)
        store.audit("arbiter", "graph.run", context_id=state.context_id,
                    detail={"status": run.status, "visited": run.visited})
        _publish(ctx, run)


def app() -> FastAPI:
    return A2AServer(CARD, ArbiterExecutor(), agent_key="arbiter").app()
