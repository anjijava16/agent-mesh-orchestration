"""The Arbiter's graph. The shape of the graph is the shape of the process.

    intake -> route -> (trace || evidence) -> (policy || abuse) -> reconcile
                                                      ^              |
                                                      |          contested
                                                      +-- renegotiate (once)
                                                                     |
                                                  disburse -> [await_approval]
                                                                     |
                                                            confirm -> notify -> END

Every node that talks to a peer is a network call with a timeout, a documented
behaviour when the peer never answers, and a checkpoint after it.

The orchestrator holds no copy of the policy. It acts only on what Statute told
it -- which is the only reason Legal Ops can ship a clause change without a
code review here.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta

from refundry import store
from refundry.a2a import A2AClient, A2AError
from refundry.agents._base import client as mcp_client
from refundry.agents.arbiter import jev_router
from refundry.agents.arbiter.graph_engine import END, Graph, Interrupt
from refundry.agents.arbiter.network import client_for, skill_of
from refundry.config import settings
from refundry.models import (
    AbuseScore,
    CaseState,
    DisbursementResult,
    EvidenceReport,
    OrderFacts,
    PolicyVerdict,
    SellerResponse,
)

graph = Graph("intake")


def _case_mcp():
    return mcp_client("case_mgmt", caller="arbiter")


async def _ask(agent: str, payload: dict, state: CaseState, text: str = "",
               task_id: str = "") -> dict:
    """One A2A delegation, with the failure behaviour written down."""
    cl = client_for(agent)
    payload = {"skill": skill_of(agent), **payload}
    try:
        task = await cl.send(payload, context_id=state.context_id,
                             text=text or skill_of(agent), task_id=task_id)
    except (A2AError, Exception) as exc:
        # A peer that never answers degrades that one signal. It does not take
        # the case down, and the trail says which input is missing.
        state.log(agent, "unreachable", f"{type(exc).__name__}: {exc}")
        store.audit("arbiter", "a2a.unreachable", target=agent,
                    context_id=state.context_id, detail=str(exc))
        return {}
    state.log(agent, task["status"]["state"], A2AClient.say(task))
    return task


# ---------------------------------------------------------------------------
# intake
# ---------------------------------------------------------------------------


@graph.node("intake")
async def intake(state: CaseState, resume) -> str:
    state.deadline = datetime.utcnow() + timedelta(days=settings.claim_window_days)

    # Insertion point 1: Jev classifies before any agent is woken.
    jev_router.triage(state)

    await _case_mcp().call(
        "open_case", case_id=state.case_id, context_id=state.context_id,
        order_ref=state.claim.order_ref, buyer_ref=state.claim.buyer_ref,
        narrative=state.claim.narrative)
    await _case_mcp().call("set_status", case_id=state.case_id,
                           status="investigating")
    state.status = "investigating"
    state.log("arbiter", "opened",
              f"{state.case_id} classified as {state.claim_type}")
    return "trace"


# ---------------------------------------------------------------------------
# fan-out 1: Tracer  ||  Witness
# ---------------------------------------------------------------------------


@graph.node("trace")
async def trace(state: CaseState, resume) -> str:
    """Tracer always runs. Witness only if there is evidence to read -- that is
    insertion point 2, and it is what stops the blind fan-out."""
    order_task = _ask("tracer", {"order_ref": state.claim.order_ref}, state)

    # We need the order before we can know whether the seller is third party,
    # so routing happens in two halves: evidence now, seller after.
    state.needs_evidence = bool(state.claim.evidence_refs)
    jobs = [order_task]
    if state.needs_evidence:
        jobs.append(_ask("witness",
                         {"evidence_refs": state.claim.evidence_refs}, state))

    results = await asyncio.gather(*jobs)

    facts = A2AClient.result(results[0], "order_facts") if results[0] else {}
    if facts:
        state.order = OrderFacts(**facts)
    if state.needs_evidence and len(results) > 1 and results[1]:
        ev = A2AClient.result(results[1], "evidence")
        if ev:
            state.evidence = EvidenceReport(**ev)
            # Insertion point 3: a gate, not an essay. Three labels, and the
            # answer branches the case rather than being read by a person.
            origin, confidence = jev_router.damage_origin(
                state, [f.statement for f in state.evidence.facts])
            state.routing["damage_origin"] = {"origin": origin,
                                              "confidence": confidence}
            if origin == "use":
                # The evidence argues against the buyer's account. Record it;
                # Statute still rules, and Sentry gets the honest input.
                state.evidence.damage_consistent_with_transit = False
                state.log("jev", "damage_origin",
                          f"evidence reads as wear, not transit "
                          f"(confidence {confidence:.2f})")

    jev_router.route(state)
    return "assess"


# ---------------------------------------------------------------------------
# fan-out 2: Statute  ||  Sentry
# ---------------------------------------------------------------------------


@graph.node("assess")
async def assess(state: CaseState, resume) -> str:
    if state.order is None:
        state.log("arbiter", "blocked", "no order facts; cannot assess")
        return "notify"

    policy = _ask("statute", {
        "claim_type": state.claim_type,
        "order_total": state.order.total,
        "days_since_delivery": state.order.days_since_delivery,
        "seller_ref": state.order.seller_ref,
    }, state)

    abuse = _ask("sentry", {
        "buyer_ref": state.claim.buyer_ref,
        "seller_ref": state.order.seller_ref,
    }, state)

    ptask, atask = await asyncio.gather(policy, abuse)

    if ptask:
        v = A2AClient.result(ptask, "verdict")
        if v:
            state.verdict = PolicyVerdict(**v)
    if atask:
        a = A2AClient.result(atask, "abuse_score")
        if a:
            state.abuse = AbuseScore(**a)

    return "consult_seller" if state.needs_seller else "reconcile"


# ---------------------------------------------------------------------------
# the seller, across the trust boundary
# ---------------------------------------------------------------------------


@graph.node("consult_seller")
async def consult_seller(state: CaseState, resume) -> str:
    task = await _ask("counterparty", {
        "order_total": state.order.total if state.order else 0.0,
        "claim_type": state.claim_type,
        "evidence_summary": state.evidence.summary if state.evidence else "",
    }, state, text="respond_to_claim")

    if not task:
        # 60s deadline blew. Proceed without them; the card says this is what
        # happens, so it is not a surprise to the seller either.
        state.seller = SellerResponse(posture="silent", offered_amount=0.0,
                                      message="no response within the deadline",
                                      responded=False)
        return "reconcile"

    raw = A2AClient.result(task, "seller_response")
    if raw:
        state.seller = SellerResponse(**raw)
        # Insertion point 3: classify their prose into a posture we can branch on.
        posture = jev_router.seller_posture(state, state.seller.message)
        state.routing["seller_posture_jev"] = posture
    return "reconcile"


# ---------------------------------------------------------------------------
# reconcile, and the two renegotiations
# ---------------------------------------------------------------------------


def _contested(state: CaseState) -> str | None:
    """Who disagrees with whom, if anyone."""
    if (state.abuse and state.abuse.recommends_manual_review
            and state.verdict and state.verdict.covered
            and not state.renegotiated_abuse):
        return "abuse"
    if (state.seller and state.seller.posture in ("counters", "disputes")
            and state.verdict and state.verdict.covered
            and not state.renegotiated_seller):
        return "seller"
    return None


@graph.node("reconcile")
async def reconcile(state: CaseState, resume) -> str:
    which = _contested(state)
    if which == "abuse":
        state.log("arbiter", "contested",
                  "Sentry recommends manual review; Statute says the claim is "
                  "covered and MKT-052 says a score is not a ground for denial")
        return "renegotiate_abuse"
    if which == "seller":
        state.log("arbiter", "contested",
                  f"seller {state.seller.posture} at "
                  f"${state.seller.offered_amount:,.2f}; the guarantee sets a floor")
        return "renegotiate_seller"
    return "disburse"


@graph.node("renegotiate_abuse")
async def renegotiate_abuse(state: CaseState, resume) -> str:
    """Not 'ignore your score'. The same skill, the same agent, a fuller brief.

    Sentry is free to come back with the same number. It re-scores itself, and
    the orchestrator does not touch the figure either way.
    """
    state.renegotiated_abuse = True
    seller_defect = False
    if state.order:
        try:
            seller = await mcp_client("catalog", caller="arbiter").call(
                "get_seller_policy", seller_ref=state.order.seller_ref)
            seller_defect = bool(seller.get("defect_signals"))
        except Exception:
            pass

    task = await _ask("sentry", {
        "buyer_ref": state.claim.buyer_ref,
        "seller_ref": state.order.seller_ref if state.order else "",
        "evidence_supports_transit": (
            state.evidence.damage_consistent_with_transit if state.evidence else None),
        "seller_defect_signal": seller_defect,
    }, state, text="score_abuse (re-ask, with the evidence attached)")

    if task:
        a = A2AClient.result(task, "abuse_score")
        if a:
            before = state.abuse.score if state.abuse else None
            state.abuse = AbuseScore(**a)
            state.log("arbiter", "re-scored",
                      f"{before} -> {state.abuse.score} with evidence attached")
    return "reconcile"


CAP = re.compile(r"\b(MKT-\d{3})\b")


@graph.node("renegotiate_seller")
async def renegotiate_seller(state: CaseState, resume) -> str:
    """Re-ask with the clause as a hard constraint on the next proposal.

    The clause id is read out of Statute's verdict. The Arbiter never looked it
    up and holds no copy of the policy book.
    """
    state.renegotiated_seller = True
    clause = state.verdict.governing_clause if state.verdict else ""
    if not clause and state.verdict and state.verdict.reasoning:
        found = CAP.search(state.verdict.reasoning)
        clause = found.group(1) if found else ""

    task = await _ask("counterparty", {
        "order_total": state.order.total if state.order else 0.0,
        "claim_type": state.claim_type,
        "hard_constraint": clause,
        "evidence_summary": state.evidence.summary if state.evidence else "",
    }, state, text=f"respond_to_claim (re-ask, with {clause} as a hard constraint)")

    if task:
        raw = A2AClient.result(task, "seller_response")
        if raw:
            before = state.seller.offered_amount if state.seller else 0.0
            state.seller = SellerResponse(**raw)
            state.log("arbiter", "seller moved",
                      f"${before:,.2f} -> ${state.seller.offered_amount:,.2f} "
                      f"({state.seller.posture})")
    return "reconcile"


# ---------------------------------------------------------------------------
# money
# ---------------------------------------------------------------------------


@graph.node("disburse")
async def disburse(state: CaseState, resume) -> str:
    if not state.verdict or not state.verdict.covered:
        state.status = "declined"
        state.log("arbiter", "declined", "no marketplace guarantee covers this claim")
        return "notify"

    # Insertion point 4: the confidence gate. A calibrated probability decides
    # whether this can resolve on the amount rule alone.
    auto_ok, confidence, why = jev_router.confidence_gate(state)
    state.routing["auto_resolve"] = {"ok": auto_ok, "confidence": confidence,
                                     "why": why}
    state.log("jev", "confidence_gate", why, confidence=confidence)

    task = await _ask("treasury", {
        "case_id": state.case_id,
        "entitled_amount": state.verdict.entitled_amount,
        "tender": state.order.tender if state.order else "card",
        "citations": [c.model_dump() for c in state.verdict.citations],
        "seller_offer": state.seller.offered_amount if state.seller else 0.0,
        "abuse_note": state.abuse.explain() if state.abuse else "",
    }, state, text="disburse")

    if not task:
        state.status = "failed"
        state.log("arbiter", "failed", "treasury unreachable; no money moved")
        return "notify"

    state.routing["treasury_task_id"] = task["id"]
    draft = A2AClient.result(task, "draft")
    if draft:
        from refundry.models import Disbursement
        state.draft = Disbursement(**{k: v for k, v in draft.items()
                                      if k != "case_id"})

    if task["status"]["state"] == "input-required":
        state.status = "awaiting_approval"
        await _case_mcp().call("set_status", case_id=state.case_id,
                               status="awaiting_approval")
        return "await_approval"

    result = A2AClient.result(task, "result")
    if result:
        state.result = DisbursementResult(**result)
        state.status = "resolved" if state.result.status == "posted" else "declined"
    return "notify"


@graph.node("await_approval")
async def await_approval(state: CaseState, resume) -> str:
    """The pause.

    Treasury moved ITS task to input-required. This node forwards that state
    onto the Arbiter's own task and stops. No worker is blocked; the state is
    checkpointed and the task keeps its id for as long as the person takes.
    """
    if resume is None:
        raise Interrupt({
            "case_id": state.case_id,
            "action": state.draft.action if state.draft else "refund",
            "amount": state.draft.amount if state.draft else 0.0,
            "tender": state.draft.tender if state.draft else "card",
            "citations": [c.model_dump() for c in state.draft.citations]
            if state.draft else [],
            "abuse": state.abuse.explain() if state.abuse else "",
            "confidence": state.routing.get("auto_resolve", {}),
            "question": (f"Approve ${state.draft.amount:,.2f} against "
                         f"{state.order.seller_ref if state.order else 'the seller'}?"),
        })

    if not resume.get("approved"):
        state.status = "declined"
        state.log("arbiter", "declined by approver", resume.get("note", ""))
        return "notify"

    state.approver = resume.get("approver") or resume.get("user") or ""
    state.log("arbiter", "approved", f"by {state.approver}")
    return "confirm"


@graph.node("confirm")
async def confirm(state: CaseState, resume) -> str:
    """Send the approval back on Treasury's ORIGINAL task id, not a new one."""
    task_id = state.routing.get("treasury_task_id", "")
    task = await _ask("treasury", {
        "case_id": state.case_id,
        "approved": True,
        "approver": state.approver,
    }, state, text="approve", task_id=task_id)

    if task:
        result = A2AClient.result(task, "result")
        if result:
            state.result = DisbursementResult(**result)
            state.status = ("resolved" if state.result.status == "posted"
                            else "declined")
    return "notify"


@graph.node("notify")
async def notify(state: CaseState, resume) -> str:
    final = {"resolved": "resolved", "declined": "declined",
             "awaiting_approval": "awaiting_approval"}.get(state.status, "resolved")
    try:
        await _case_mcp().call("set_status", case_id=state.case_id, status=final)
        await _case_mcp().call("append_note", case_id=state.case_id,
                               author="arbiter",
                               note=state.result.message if state.result
                               else f"case closed as {final}")
        await _case_mcp().call("put_case", case_id=state.case_id,
                               record=state.model_dump(mode="json"))
    except Exception as exc:
        state.log("arbiter", "case write failed", str(exc))
    state.log("arbiter", "closed", final)
    return END
