from refundry.a2a import Skill, build_card
from refundry.config import a2a_url, settings

CARD = build_card(
    name="Treasury",
    description="Chooses the tender, executes the disbursement, and refuses to "
                "do either without a signature above the threshold.",
    url=a2a_url("treasury"),
    version="4.0.0",
    organization="Northwind Market · Payments",
    skills=[Skill(
        id="disburse",
        name="Disburse a refund",
        description=(
            "Drafts and executes a refund. Above the "
            f"${settings.auto_approval_limit:,.2f} auto-approval threshold the "
            "task moves to input-required and waits for a named approver "
            "(MKT-060). Requires a citation; a draft without one is refused."),
        tags=["payments", "money", "approval"],
    )],
)
