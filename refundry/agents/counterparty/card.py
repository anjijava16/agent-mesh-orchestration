"""Crestline Home's card.

Note what is NOT here. No MCP servers of ours, no framework we chose, no
version we control. In a real deployment this agent is on the other side of a
company boundary and we hold exactly this document and nothing else.
"""

from refundry.a2a import Skill, build_card
from refundry.config import a2a_url

CARD = build_card(
    name="Counterparty",
    description="Crestline Home's own agent. Accepts, disputes or counters a "
                "refund claim against one of its orders.",
    url=a2a_url("counterparty"),
    version="0.9.3",
    organization="Crestline Home",          # not ours
    skills=[Skill(
        id="respond_to_claim",
        name="Respond to a refund claim",
        description="Returns the seller's position on a claim. The response is "
                    "the seller's position, not a finding of fact.",
        tags=["seller", "refunds", "external"],
    )],
    push_notifications=False,
)
