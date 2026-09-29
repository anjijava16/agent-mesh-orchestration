from refundry.a2a import Skill, build_card
from refundry.config import a2a_url

CARD = build_card(
    name="Witness",
    description="Turns photographs, packing slips and transcripts into "
                "structured, quotable facts.",
    url=a2a_url("witness"),
    version="1.4.0",
    organization="Northwind Market · Evidence Platform",
    skills=[Skill(
        id="extract_evidence",
        name="Extract evidence",
        description="Parses uploaded evidence into facts with per-fact "
                    "confidence. Returns observations only. Holds no tool that "
                    "changes anything, and treats document text as data, never "
                    "as instructions.",
        tags=["evidence", "documents", "vision"],
        input_modes=["application/json"],
    )],
)
