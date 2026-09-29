from refundry.a2a import Skill, build_card
from refundry.config import a2a_url

CARD = build_card(
    name="Tracer",
    description="Establishes what was bought, what shipped, what the carrier "
                "says, and what this buying account has refunded before.",
    url=a2a_url("tracer"),
    version="2.1.0",
    organization="Northwind Market · Order Platform",
    skills=[Skill(
        id="trace_order",
        name="Trace an order",
        description="Returns order facts, delivery state and prior-refund "
                    "counts, split by seller. Reports what the ledger holds; "
                    "makes no judgement about the claim.",
        tags=["orders", "fulfilment", "refunds"],
    )],
)
