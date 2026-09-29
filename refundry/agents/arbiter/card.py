from refundry.a2a import Skill, build_card
from refundry.config import a2a_url

CARD = build_card(
    name="Arbiter",
    description="Owns a refund case: classifies it, plans, routes to "
                "specialists, holds the clock, and is the one thing a human "
                "talks to.",
    url=a2a_url("arbiter"),
    version="5.1.0",
    organization="Northwind Market · Refund Platform",
    skills=[Skill(
        id="resolve_refund",
        name="Resolve a refund claim",
        description="Files and resolves a claim end to end. May move to "
                    "input-required when a named approver is needed; the "
                    "approval is sent as a message on the same task id.",
        tags=["refunds", "orchestration"],
    )],
)
