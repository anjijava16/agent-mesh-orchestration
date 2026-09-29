"""Treasury's service. Decides whether money moves, and how much.

This is the only agent that holds the payments scope, and the only place the
idempotency key is minted. Both facts are load-bearing: a prompt cannot talk
its way past a credential that is not in the process.
"""

from __future__ import annotations

from refundry import ids
from refundry.agents._base import client
from refundry.config import settings
from refundry.models import Citation, Disbursement, DisbursementResult


def draft(*, case_id: str, entitled_amount: float, tender: str,
          citations: list[dict], seller_offer: float = 0.0) -> Disbursement:
    """What we propose to pay. The marketplace guarantee sets the floor: a
    seller's partial offer does not reduce what the buyer is entitled to."""
    amount = round(max(entitled_amount, 0.0), 2)
    cites = [Citation(**c) if isinstance(c, dict) else c for c in citations]
    rationale = (
        f"${amount:,.2f} to the original tender under "
        f"{cites[0].clause_id if cites else 'no clause'}."
    )
    if seller_offer and seller_offer < amount:
        rationale += (f" The seller offered ${seller_offer:,.2f}; the guarantee "
                      f"sets the floor, so the offer does not reduce it.")
    return Disbursement(
        action="refund" if amount > 0 else "decline",
        amount=amount,
        tender=tender if tender in ("card", "wallet", "split") else "card",
        idempotency_key=ids.idempotency_key(case_id, amount),
        citations=cites,
        rationale=rationale,
    )


def needs_signature(amount: float) -> bool:
    return amount >= settings.auto_approval_limit


async def execute(*, case_id: str, disbursement: Disbursement,
                  approver: str = "", context_id: str = "") -> DisbursementResult:
    """Call the one server that can move money."""
    if not disbursement.citations:
        # An outcome with no citation never reaches an approver, and never
        # reaches the ledger either.
        return DisbursementResult(
            status="declined",
            message="refused: a disbursement without a policy citation cannot "
                    "be executed or approved",
        )

    claims = {"idempotency-key": disbursement.idempotency_key}
    payments = client("payments", caller="treasury", claims=claims)

    kwargs = {
        "case_id": case_id,
        "amount": disbursement.amount,
        "tender": disbursement.tender,
        "idempotency_key": disbursement.idempotency_key,
    }
    if approver:
        kwargs["approver"] = approver
        kwargs["approval_claim"] = ids.approval_claim(
            case_id, disbursement.amount, approver)

    posted = await payments.call("issue_refund", **kwargs)
    return DisbursementResult(
        status="posted",
        refund_ref=posted["refund_ref"],
        amount=posted["amount"],
        approver=posted.get("approver"),
        message=(f"Refund {posted['refund_ref']} posted: "
                 f"${posted['amount']:,.2f} to {posted['tender']}"
                 + (" (replay, no second refund minted)" if posted.get("replay") else "")),
    )
