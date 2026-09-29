"""Statute's service. Decides which clauses are broken. Binding."""

from __future__ import annotations

from refundry.agents._base import client
from refundry.agents.statute import rules
from refundry.models import Citation, PolicyVerdict


async def assess(*, claim_type: str, order_total: float,
                 days_since_delivery: int | None, seller_ref: str,
                 context_id: str = "") -> tuple[PolicyVerdict, list[dict]]:
    policy = client("policy_kb", caller="statute")
    catalog = client("catalog", caller="statute")

    found = await policy.call("clauses_for", claim_type=claim_type)
    governing_candidates = found.get("governing") or []

    evaluations = [
        rules.evaluate(c, claim_type=claim_type,
                       days_since_delivery=days_since_delivery,
                       order_total=order_total)
        for c in governing_candidates
    ]
    chosen = rules.pick_governing(evaluations)

    seller = await catalog.call("get_seller_policy", seller_ref=seller_ref)
    seller_terms = seller.get("return_policy", {})

    citations: list[Citation] = []
    clause_text = {c["clause_id"]: c for c in governing_candidates}
    if chosen:
        c = clause_text[chosen["clause_id"]]
        citations.append(Citation(clause_id=c["clause_id"], title=c["title"],
                                  quote=c["text"]))
    for advisory in found.get("advisory", []):
        citations.append(Citation(clause_id=advisory["clause_id"],
                                  title=advisory["title"], quote=advisory["text"]))
    for threshold in found.get("thresholds", []):
        citations.append(Citation(clause_id=threshold["clause_id"],
                                  title=threshold["title"], quote=threshold["text"]))

    verdict = PolicyVerdict(
        covered=bool(chosen),
        governing_clause=chosen["clause_id"] if chosen else "none",
        buyer_owes_shipping=(chosen["buyer_owes_shipping"] if chosen
                             else bool(seller_terms.get("buyer_pays_return_shipping"))),
        within_window=chosen["within_window"] if chosen else False,
        entitled_amount=chosen["entitled_amount"] if chosen else 0.0,
        citations=citations,
    )
    return verdict, evaluations
