from refundry.a2a import Skill, build_card
from refundry.config import a2a_url

CARD = build_card(
    name="Statute",
    description="Rules on which policy governs a claim -- the marketplace "
                "guarantee, the seller's own terms, or consumer law -- and "
                "cites the clause.",
    url=a2a_url("statute"),
    version="3.0.1",
    organization="Northwind Market · Legal Ops",
    skills=[Skill(
        id="assess_eligibility",
        name="Assess eligibility",
        description="Returns a binding verdict with citations. The ruling is "
                    "evaluated from the structured half of each clause, not "
                    "from a paraphrase. An abuse score is never a ground for "
                    "denying a covered claim.",
        tags=["policy", "compliance", "refunds"],
    )],
)
