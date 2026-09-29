"""Crestline Home's logic.

This lives in our repo only because the demo has to run on one machine. Treat
it as a black box: the orchestrator may not import it, may not inspect it, and
may not rely on anything it does beyond the output schema on the card.

Its behaviour is a plausible commercial one. It opens by disputing and offering
a partial, because that is cheaper. When it is re-asked with a marketplace
clause presented as a hard constraint, it accepts -- because arguing with a
guarantee it has already agreed to costs more than the refund.
"""

from __future__ import annotations

from refundry.models import SellerResponse

PARTIAL_FRACTION = 0.40


def respond(*, order_total: float, claim_type: str,
            hard_constraint: str = "", evidence_summary: str = "") -> SellerResponse:
    if hard_constraint:
        return SellerResponse(
            posture="accepts",
            offered_amount=round(order_total, 2),
            message=(f"Accepted in full under {hard_constraint}. We maintain the "
                     f"unit left our facility intact, but we do not contest the "
                     f"marketplace guarantee."),
        )

    if claim_type == "damaged":
        return SellerResponse(
            posture="counters",
            offered_amount=round(order_total * PARTIAL_FRACTION, 2),
            message=(f"We dispute that the unit shipped damaged. Our packing "
                     f"photographs show it intact at despatch. As a gesture we "
                     f"offer {int(PARTIAL_FRACTION * 100)}% "
                     f"(${order_total * PARTIAL_FRACTION:,.2f}) and the buyer "
                     f"returns the item at their own cost."),
        )

    return SellerResponse(
        posture="disputes", offered_amount=0.0,
        message="We do not accept this claim on the information provided.",
    )
