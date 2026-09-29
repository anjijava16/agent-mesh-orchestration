"""risk -- refund-abuse signals.

Everything here is ADVISORY. MKT-052 says so, Sentry's Agent Card says so, and
the orchestrator is built so that a high score cannot by itself deny a claim
that a marketplace guarantee covers.
"""

from __future__ import annotations

from refundry.mcp import MCPServer, ToolError
from refundry.servers._seed import load

mcp = MCPServer("risk", scope="risk.read", risk="medium")


def _account(buyer_ref: str) -> dict:
    for a in load("risk")["accounts"]:
        if a["buyer_ref"] == buyer_ref:
            return a
    raise ToolError(f"no risk profile for {buyer_ref!r}")


@mcp.tool(read_only=True)
def score_account(buyer_ref: str) -> dict:
    """Raw account-level abuse signals. Advisory, never a ground for denial."""
    a = _account(buyer_ref)
    return {
        "buyer_ref": buyer_ref,
        "refunds_90d": a["refunds_90d"],
        "refunds_value_90d": a["refunds_value_90d"],
        "refund_rate_percentile_90d": a["refund_rate_percentile_90d"],
        "tenure_days": a["tenure_days"],
        "orders_lifetime": a["orders_lifetime"],
        "chargebacks_lifetime": a["chargebacks_lifetime"],
        "advisory": True,
    }


@mcp.tool(read_only=True)
def percentile_for(refunds_90d: int) -> dict:
    """The cohort percentile for a given refund count in 90 days.

    Exists so that re-attributing refunds to a seller re-reads a real percentile
    rather than applying an arbitrary discount to the old one.
    """
    table = load("risk")["percentile_by_refund_count_90d"]
    key = str(min(int(refunds_90d), max(int(k) for k in table)))
    return {"refunds_90d": int(refunds_90d), "percentile": table[key]}


@mcp.tool(read_only=True)
def link_accounts(buyer_ref: str) -> dict:
    """Accounts sharing a device, address or instrument with this one."""
    a = _account(buyer_ref)
    return {"buyer_ref": buyer_ref, "linked_accounts": a["linked_accounts"],
            "address_changes_90d": a["address_changes_90d"]}


@mcp.tool(read_only=True)
def velocity_window(buyer_ref: str, days: int = 90) -> dict:
    """Refund velocity, and the percentile it lands in for the cohort."""
    a = _account(buyer_ref)
    return {"buyer_ref": buyer_ref, "days": days, "refunds": a["refunds_90d"],
            "percentile": a["refund_rate_percentile_90d"]}
