"""orders -- what was bought, what shipped, what the carrier says."""

from __future__ import annotations

from datetime import date

from refundry.mcp import MCPServer, ToolError
from refundry.servers._seed import load

mcp = MCPServer("orders", scope="refunds.order.read", risk="low")


def _find(order_ref: str) -> dict:
    for o in load("orders")["orders"]:
        if o["order_ref"] == order_ref:
            return o
    raise ToolError(
        f"order_ref {order_ref!r} is not in the ledger; check the case record for "
        f"the order the claim was filed against",
        hint="known refs begin NW-",
    )


@mcp.tool(read_only=True)
def get_order(order_ref: str) -> dict:
    """The order as the ledger holds it: lines, totals, tender and seller.

    Does not include carrier events -- call get_fulfilment for those.
    """
    o = _find(order_ref)
    total = round(sum(ln["qty"] * ln["unit_price"] for ln in o["lines"]), 2)
    return {
        "order_ref": o["order_ref"],
        "buyer_ref": o["buyer_ref"],
        "placed_at": o["placed_at"],
        "lines": o["lines"],
        "total": total,
        "seller_ref": o["seller_ref"],
        "seller_is_third_party": o["seller_is_third_party"],
        "tender": o["tender"],
        "capture_intact": o.get("capture_intact", True),
    }


@mcp.tool(read_only=True)
def get_fulfilment(order_ref: str) -> dict:
    """Delivery state and the carrier's own event list for one order."""
    o = _find(order_ref)
    delivered = o.get("delivered_at")
    days = None
    if delivered:
        days = (date.fromisoformat("2026-09-28") - date.fromisoformat(delivered)).days
    return {
        "order_ref": order_ref,
        "delivered_at": delivered,
        "days_since_delivery": days,
        "carrier_status": o.get("carrier_status", "unknown"),
        "events": o.get("carrier_events", []),
    }


@mcp.tool(read_only=True)
def carrier_events(order_ref: str) -> dict:
    """Just the carrier scan list, for when the delivery story is contested."""
    return {"order_ref": order_ref, "events": _find(order_ref).get("carrier_events", [])}


@mcp.tool(read_only=True)
def prior_refunds(buyer_ref: str, days: int = 90) -> dict:
    """Refunds already granted to a buying account inside a rolling window.

    Also splits them by seller, because four refunds against one seller and
    four refunds against four sellers are very different signals.
    """
    rows = [r for r in load("orders")["prior_refunds"] if r["buyer_ref"] == buyer_ref]
    by_seller: dict[str, int] = {}
    for r in rows:
        by_seller[r["seller_ref"]] = by_seller.get(r["seller_ref"], 0) + 1
    return {
        "buyer_ref": buyer_ref,
        "window_days": days,
        "count": len(rows),
        "value": round(sum(r["amount"] for r in rows), 2),
        "by_seller": by_seller,
        "refunds": rows,
    }
