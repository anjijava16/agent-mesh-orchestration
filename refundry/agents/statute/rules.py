"""The ruling, in ordinary Python.

Retrieval decides which clauses are worth EXPLAINING. This decides which are
BROKEN. A buyer is never denied, or waved through, because a model paraphrased
a paragraph.
"""

from __future__ import annotations


def evaluate(clause: dict, *, claim_type: str, days_since_delivery: int | None,
             order_total: float) -> dict:
    """Apply one clause's structured rule to the facts."""
    rule = clause.get("rule") or {}
    applies = claim_type in (rule.get("applies_to") or [])
    window = rule.get("window_days")
    within = True if window is None or days_since_delivery is None \
        else days_since_delivery <= window

    entitled = 0.0
    if applies and within:
        entitled = round(order_total * float(rule.get("refund_fraction", 1.0)), 2)

    return {
        "clause_id": clause["clause_id"],
        "title": clause["title"],
        "applies": applies,
        "within_window": within,
        "buyer_owes_shipping": bool(rule.get("buyer_owes_shipping", False)),
        "overrides_seller_policy": bool(rule.get("overrides_seller_policy", False)),
        "entitled_amount": entitled,
        "window_days": window,
    }


def pick_governing(evaluations: list[dict]) -> dict | None:
    """A clause that overrides the seller's policy wins. Otherwise the first
    that applies and is in window."""
    live = [e for e in evaluations if e["applies"] and e["within_window"]]
    if not live:
        return None
    live.sort(key=lambda e: (not e["overrides_seller_policy"], -e["entitled_amount"]))
    return live[0]
