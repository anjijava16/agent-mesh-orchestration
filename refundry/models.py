"""The wire contract.

These pydantic models are the only thing the agents share. They define what
crosses an A2A boundary, so a change here is a version bump on somebody's card.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ClaimType = Literal["damaged", "not_received", "wrong_item", "quality", "unknown"]
Tender = Literal["card", "wallet", "split"]
SellerPosture = Literal["accepts", "counters", "disputes", "silent"]


# --------------------------------------------------------------------------
# What comes in
# --------------------------------------------------------------------------


class Claim(BaseModel):
    order_ref: str
    buyer_ref: str
    narrative: str
    evidence_refs: list[str] = Field(default_factory=list)
    filed_at: datetime = Field(default_factory=datetime.utcnow)


# --------------------------------------------------------------------------
# Tracer
# --------------------------------------------------------------------------


class OrderLine(BaseModel):
    sku: str
    title: str
    qty: int
    unit_price: float


class OrderFacts(BaseModel):
    order_ref: str
    placed_at: date
    delivered_at: date | None
    days_since_delivery: int | None
    lines: list[OrderLine]
    total: float
    seller_ref: str
    seller_is_third_party: bool
    tender: Tender
    carrier_status: str
    prior_refunds_90d: int
    prior_refunds_value_90d: float
    prior_refunds_same_seller_90d: int
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Witness
# --------------------------------------------------------------------------


class Fact(BaseModel):
    source_ref: str
    kind: str
    statement: str
    confidence: float


class EvidenceReport(BaseModel):
    facts: list[Fact]
    legible: bool
    damage_consistent_with_transit: bool | None
    serial_matches_shipment: bool | None
    summary: str = ""


# --------------------------------------------------------------------------
# Statute
# --------------------------------------------------------------------------


class Citation(BaseModel):
    clause_id: str
    title: str
    quote: str


class PolicyVerdict(BaseModel):
    covered: bool
    governing_clause: str
    buyer_owes_shipping: bool
    within_window: bool
    entitled_amount: float
    citations: list[Citation]
    reasoning: str = ""


# --------------------------------------------------------------------------
# Sentry
# --------------------------------------------------------------------------


class AbuseScore(BaseModel):
    score: float
    band: Literal["low", "medium", "high"]
    recommends_manual_review: bool
    drivers: list[str]
    # Set when the score was produced with the evidence attached, which is what
    # lets a second look legitimately disagree with the first.
    evidence_considered: bool = False
    explanation: str = ""

    def explain(self) -> str:
        return self.explanation or "; ".join(self.drivers)


# --------------------------------------------------------------------------
# Counterparty — the seller's agent, which we do not own
# --------------------------------------------------------------------------


class SellerResponse(BaseModel):
    posture: SellerPosture
    offered_amount: float
    message: str
    responded: bool = True


# --------------------------------------------------------------------------
# Treasury
# --------------------------------------------------------------------------


class Disbursement(BaseModel):
    action: Literal["refund", "store_credit", "decline"]
    amount: float
    tender: Tender
    idempotency_key: str
    citations: list[Citation] = Field(default_factory=list)
    rationale: str = ""


class DisbursementResult(BaseModel):
    status: Literal["posted", "needs_approval", "declined"]
    refund_ref: str | None = None
    amount: float = 0.0
    approver: str | None = None
    message: str = ""


# --------------------------------------------------------------------------
# The case, as the orchestrator holds it
# --------------------------------------------------------------------------


class CaseState(BaseModel):
    case_id: str
    context_id: str
    claim: Claim

    claim_type: ClaimType = "unknown"
    needs_evidence: bool = True
    needs_seller: bool = True

    order: OrderFacts | None = None
    evidence: EvidenceReport | None = None
    verdict: PolicyVerdict | None = None
    abuse: AbuseScore | None = None
    seller: SellerResponse | None = None

    renegotiated_abuse: bool = False
    renegotiated_seller: bool = False

    draft: Disbursement | None = None
    result: DisbursementResult | None = None
    approver: str | None = None

    status: str = "open"
    deadline: datetime | None = None
    routing: dict = Field(default_factory=dict)
    timeline: list[dict] = Field(default_factory=list)

    def log(self, actor: str, event: str, detail: str = "", **extra) -> None:
        self.timeline.append({
            "at": datetime.utcnow().isoformat(timespec="seconds"),
            "actor": actor,
            "event": event,
            "detail": detail,
            **extra,
        })
