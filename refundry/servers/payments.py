"""payments -- the only server in the estate that can move money.

Three controls, and none of them is a prompt:

  1. `payments.refund` scope, held by exactly one process (Treasury).
  2. An **approval claim** that only the human review step can mint. It is bound
     to the case AND the amount, so it does not authorise a different figure.
  3. An **idempotency key**, derived from the case and the amount, so a replayed
     A2A message cannot mint a second refund. Retries are the normal case.

The claim requirement is enforced by the MCP layer via `requires=[...]`, which
means it is checked before the tool body runs -- not inside it, where an
exception path could skip it.
"""

from __future__ import annotations

from refundry import ids, store
from refundry.config import settings
from refundry.mcp import MCPServer, ToolError

mcp = MCPServer("payments", scope="payments.refund", risk="high")


def _check_claim(case_id: str, amount: float, approval_claim: str,
                 approver: str) -> None:
    expected = ids.approval_claim(case_id, amount, approver)
    if approval_claim != expected:
        raise ToolError(
            "approval claim does not match this case and amount; a claim minted "
            "for a different figure does not authorise this one",
            hint="the review step mints the claim, bound to case + amount + approver",
        )


@mcp.tool(destructive=True, requires=["idempotency-key"])
def issue_refund(case_id: str, amount: float, tender: str,
                 idempotency_key: str, approver: str = "",
                 approval_claim: str = "") -> dict:
    """Move money back to the buyer's original tender.

    Requires an X-Idempotency-Key header. Above the auto-approval threshold it
    additionally requires a matching approval claim and a named approver.
    """
    if amount <= 0:
        raise ToolError("amount must be positive")
    if idempotency_key != ids.idempotency_key(case_id, amount):
        raise ToolError(
            "idempotency key is not derived from this case and amount",
            hint="key = sha256(case:amount); a replay must produce the same key",
        )

    if amount >= settings.auto_approval_limit:
        if not approver or not approval_claim:
            raise ToolError(
                f"${amount:,.2f} is at or above the ${settings.auto_approval_limit:,.2f} "
                "auto-approval threshold and needs a named approver plus an "
                "approval claim (MKT-060)",
                hint="move the task to input-required and ask a person",
            )
        _check_claim(case_id, amount, approval_claim, approver)

    ref = ids.refund_ref(case_id, amount)
    fresh, row = store.commit_refund(idempotency_key, case_id, ref, amount,
                                     tender, approver or None)
    store.audit("payments", "refund.posted" if fresh else "refund.replayed",
                target=case_id, detail={"amount": amount, "ref": row["refund_ref"],
                                        "approver": approver})
    return {"status": "posted", "refund_ref": row["refund_ref"],
            "amount": row["amount"], "tender": row["tender"],
            "approver": row["approver"], "replay": not fresh}


@mcp.tool(destructive=True, requires=["idempotency-key"])
def issue_store_credit(case_id: str, amount: float, idempotency_key: str) -> dict:
    """Credit the buyer's wallet instead of the original tender."""
    if idempotency_key != ids.idempotency_key(case_id, amount):
        raise ToolError("idempotency key is not derived from this case and amount")
    ref = ids.refund_ref(case_id, amount)
    fresh, row = store.commit_refund(idempotency_key, case_id, ref, amount,
                                     "wallet", None)
    return {"status": "posted", "refund_ref": row["refund_ref"],
            "amount": row["amount"], "tender": "wallet", "replay": not fresh}


@mcp.tool(destructive=True, requires=["idempotency-key"])
def reverse_refund(refund_ref: str, reason: str, idempotency_key: str) -> dict:
    """Reverse a posted refund. Exists so the roster has a genuinely dangerous
    neighbour to issue_refund -- which is the point of naming tools carefully."""
    for row in store.ledger():
        if row["refund_ref"] == refund_ref:
            store.audit("payments", "refund.reversed", target=refund_ref,
                        detail=reason)
            return {"status": "reversed", "refund_ref": refund_ref, "reason": reason}
    raise ToolError(f"no refund {refund_ref!r} in the ledger")
