"""Sentry's service. Computes the score. No model involved.

The interesting behaviour is re-attribution. Four refunds in ninety days is a
97th-percentile signal about a *buyer*. But if three of those four are against
one seller, and that seller has an open packaging defect pattern, then most of
the signal is about the *seller* wearing a buyer's face.

Re-attribution only happens when evidence has actually been supplied, which is
why the orchestrator's second ask is a fuller brief rather than an instruction
to lower the number.
"""

from __future__ import annotations

from refundry.agents._base import client
from refundry.models import AbuseScore

# Weights, stated once so the arithmetic is auditable.
W_PERCENTILE = 0.60
W_VELOCITY = 0.20
W_VALUE = 0.05
TENURE_DISCOUNT = 0.035
CONCENTRATION_FLOOR = 0.60


def _band(score: float) -> str:
    return "high" if score >= 0.60 else ("medium" if score >= 0.35 else "low")


def _compose(percentile: int, refunds: int, value: float, tenure_days: int,
             linked: int) -> float:
    score = (percentile / 100.0) * W_PERCENTILE
    score += min(refunds, 6) / 6.0 * W_VELOCITY
    score += min(value / 1000.0, 1.0) * W_VALUE
    if linked:
        score += 0.15
    if tenure_days > 365:
        score -= TENURE_DISCOUNT
    return round(max(0.0, min(1.0, score)), 4)


async def score(*, buyer_ref: str, seller_ref: str = "",
                evidence_supports_transit: bool | None = None,
                seller_defect_signal: bool = False,
                context_id: str = "") -> AbuseScore:
    risk = client("risk", caller="sentry")
    orders = client("orders", caller="sentry")

    account = await risk.call("score_account", buyer_ref=buyer_ref)
    links = await risk.call("link_accounts", buyer_ref=buyer_ref)
    priors = await orders.call("prior_refunds", buyer_ref=buyer_ref, days=90)

    refunds = account["refunds_90d"]
    value = account["refunds_value_90d"]
    percentile = account["refund_rate_percentile_90d"]
    same_seller = priors["by_seller"].get(seller_ref, 0) if seller_ref else 0
    concentration = (same_seller / refunds) if refunds else 0.0

    drivers = [
        f"{refunds} refunds in 90 days, {percentile}th percentile for the cohort",
        f"${value:,.2f} refunded in the window",
        f"{links['linked_accounts']} linked accounts",
        f"{account['tenure_days']} days of account tenure, "
        f"{account['orders_lifetime']} lifetime orders",
    ]

    considered = evidence_supports_transit is not None
    reattributed = (
        considered
        and evidence_supports_transit
        and seller_defect_signal
        and concentration >= CONCENTRATION_FLOOR
    )

    if not reattributed:
        raw = _compose(percentile, refunds, value, account["tenure_days"],
                       links["linked_accounts"])
        if considered and not reattributed and same_seller:
            drivers.append(
                f"{same_seller} of {refunds} are against {seller_ref}, but the "
                "evidence does not support re-attribution")
        return AbuseScore(
            score=raw, band=_band(raw),
            recommends_manual_review=raw >= 0.60,
            drivers=drivers, evidence_considered=considered,
        )

    # Re-attribute the concentrated refunds to the seller and re-read the
    # cohort percentile for what is left.
    same_value = round(sum(r["amount"] for r in priors["refunds"]
                           if r["seller_ref"] == seller_ref), 2)
    effective_refunds = refunds - same_seller
    effective_value = round(value - same_value, 2)
    lookup = await risk.call("percentile_for", refunds_90d=effective_refunds)
    effective_percentile = lookup["percentile"]

    raw = _compose(effective_percentile, effective_refunds, effective_value,
                   account["tenure_days"], links["linked_accounts"])

    drivers = [
        f"{same_seller} of {refunds} prior refunds are against {seller_ref}, "
        f"which has an open packaging defect pattern",
        "that is a seller signal, not a buyer signal, so it is re-attributed",
        f"on the remaining {effective_refunds} refund(s) the account sits at the "
        f"{effective_percentile}th percentile, not the {percentile}th",
        "evidence supports transit damage, which is consistent with the pattern",
    ]
    return AbuseScore(
        score=raw, band=_band(raw), recommends_manual_review=raw >= 0.60,
        drivers=drivers, evidence_considered=True,
    )
