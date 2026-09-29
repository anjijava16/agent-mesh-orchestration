"""Tracer's service. Decides what is in scope. No model involved."""

from __future__ import annotations

from refundry.agents._base import client
from refundry.models import OrderFacts, OrderLine


async def trace(order_ref: str, *, context_id: str = "") -> OrderFacts:
    orders = client("orders", caller="tracer")
    catalog = client("catalog", caller="tracer")

    order = await orders.call("get_order", order_ref=order_ref)
    fulfil = await orders.call("get_fulfilment", order_ref=order_ref)
    priors = await orders.call("prior_refunds", buyer_ref=order["buyer_ref"], days=90)

    seller = await catalog.call("get_seller_policy", seller_ref=order["seller_ref"])
    same_seller = priors["by_seller"].get(order["seller_ref"], 0)

    notes: list[str] = []
    for event in fulfil.get("events", []):
        if "exception" in event["event"] or "damaged" in event["event"]:
            notes.append(f"carrier exception on {event['at'][:10]}: {event['event']}")
    if same_seller >= 2:
        notes.append(
            f"{same_seller} of {priors['count']} prior refunds in 90 days are against "
            f"{seller['display_name']}, the same seller as this order")
    defects = seller.get("defect_signals") or {}
    if defects:
        notes.append(
            f"{seller['display_name']} has {defects['packaging_complaints_90d']} packaging "
            f"complaints in 90 days against a category baseline of "
            f"{defects['category_baseline_90d']}")

    return OrderFacts(
        order_ref=order["order_ref"],
        placed_at=order["placed_at"],
        delivered_at=fulfil.get("delivered_at"),
        days_since_delivery=fulfil.get("days_since_delivery"),
        lines=[OrderLine(**line) for line in order["lines"]],
        total=order["total"],
        seller_ref=order["seller_ref"],
        seller_is_third_party=order["seller_is_third_party"],
        tender=order["tender"],
        carrier_status=fulfil.get("carrier_status", "unknown"),
        prior_refunds_90d=priors["count"],
        prior_refunds_value_90d=priors["value"],
        prior_refunds_same_seller_90d=same_seller,
        notes=notes,
    )
