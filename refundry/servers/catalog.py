"""catalog -- items, seller terms, category rules."""

from __future__ import annotations

import json

from refundry.mcp import MCPServer, ToolError
from refundry.servers._seed import load

mcp = MCPServer("catalog", scope="catalog.read", risk="low")


@mcp.tool(read_only=True)
def get_item(sku: str) -> dict:
    """One catalogue item, including whether the category is fragile."""
    for i in load("catalog")["items"]:
        if i["sku"] == sku:
            return i
    raise ToolError(f"sku {sku!r} is not in the catalogue")


@mcp.tool(read_only=True)
def get_seller_policy(seller_ref: str) -> dict:
    """A seller's own published return policy, and any defect signals we hold.

    The policy is the seller's. Whether it governs is a question for policy-kb.
    """
    for s in load("catalog")["sellers"]:
        if s["seller_ref"] == seller_ref:
            return s
    raise ToolError(f"seller_ref {seller_ref!r} is unknown")


@mcp.tool(read_only=True)
def get_category_rules(category: str) -> dict:
    """Marketplace rules that attach to a product category."""
    rules = [r for r in load("catalog")["category_rules"] if r["category"] == category]
    return {"category": category, "rules": rules}


@mcp.resource("catalog://sellers/SEL-CRESTLINE/return-policy",
              name="Crestline Home return policy")
def crestline_policy() -> str:
    for s in load("catalog")["sellers"]:
        if s["seller_ref"] == "SEL-CRESTLINE":
            return json.dumps(s["return_policy"], indent=2)
    return "{}"
