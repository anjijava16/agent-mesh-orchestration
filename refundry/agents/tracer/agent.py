"""Tracer's model half: which discrepancy matters, and how to say it.

The service already decided what is in scope. This only writes the sentence a
person reads, and it degrades to a deterministic summary.
"""

from __future__ import annotations

from refundry.agents._base import judge
from refundry.models import OrderFacts


def _deterministic(facts: OrderFacts) -> str:
    item = facts.lines[0].title if facts.lines else "the order"
    line = (f"{item} at ${facts.total:,.2f}, delivered "
            f"{facts.days_since_delivery} days ago, carrier says "
            f"{facts.carrier_status}.")
    if facts.prior_refunds_same_seller_90d >= 2:
        line += (f" {facts.prior_refunds_90d} prior refunds in 90 days, of which "
                 f"{facts.prior_refunds_same_seller_90d} are against this same seller.")
    else:
        line += f" {facts.prior_refunds_90d} prior refunds in 90 days."
    return line


async def summarise(facts: OrderFacts, *, context_id: str = "") -> str:
    return await judge(
        "tracer",
        lambda: None,  # an LLM call would go here
        fallback=_deterministic(facts),
        context_id=context_id,
    )
