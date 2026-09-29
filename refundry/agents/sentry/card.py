from refundry.a2a import Skill, build_card
from refundry.config import a2a_url

CARD = build_card(
    name="Sentry",
    description="Scores refund-abuse risk for a buying account against "
                "velocity, linkage and category signals.",
    url=a2a_url("sentry"),
    version="3.2.0",
    organization="Northwind Market · Trust & Safety",
    skills=[Skill(
        id="score_abuse",
        name="Score refund-abuse risk",
        description="Advisory only. Never a sole ground for denying a covered "
                    "claim (MKT-052). Accepts optional evidence and order "
                    "context; a score produced with evidence attached may "
                    "legitimately differ from one produced without it.",
        tags=["risk", "refunds", "trust-and-safety"],
    )],
)
