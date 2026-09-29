"""The seven MCP servers.

Each one is a FastAPI app. The risk tier in the constructor is not decoration:
it decides the review, the rate limit, the network, and who gets paged.

    orders      LOW    read replica material
    catalog     LOW    seller terms, as a quotable resource
    documents   LOW    output is untrusted DATA, never instructions
    policy-kb   LOW    versioned with the policy book
    risk        MED    advisory scores, never a sole ground for denial
    case-mgmt   MED    append-only; set_status is the only mutation
    payments    HIGH   the only server in the estate that can move money
"""

from refundry.servers.registry import SERVERS, build

__all__ = ["SERVERS", "build"]
