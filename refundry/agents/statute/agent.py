"""Statute's model half: which clauses to quote, and how to explain them.

The ruling above is binding. This writes the two sentences a buyer reads, and
degrades to a deterministic explanation built from the same citations.
"""

from __future__ import annotations

from refundry.agents._base import judge
from refundry.models import PolicyVerdict


def _deterministic(verdict: PolicyVerdict, seller_name: str) -> str:
    if not verdict.covered:
        return ("No marketplace guarantee covers this claim on the facts given, "
                "so the seller's own return policy governs.")
    head = verdict.citations[0] if verdict.citations else None
    who = "the buyer owes nothing toward return shipping" \
        if not verdict.buyer_owes_shipping else "the buyer pays return shipping"
    return (f"{head.clause_id} {head.title} governs and overrides {seller_name}'s "
            f"return terms, so {who}. The claim is inside the window, and "
            f"${verdict.entitled_amount:,.2f} is refundable to the original tender."
            if head else "Covered.")


async def explain(verdict: PolicyVerdict, seller_name: str, *,
                  context_id: str = "") -> str:
    return await judge("statute", lambda: None,
                       fallback=_deterministic(verdict, seller_name),
                       context_id=context_id)
