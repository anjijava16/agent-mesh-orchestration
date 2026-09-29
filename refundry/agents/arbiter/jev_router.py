"""Where System One sits in the path.

Four insertion points, and each one replaces a frontier-model call that
returned a label:

    1. intake      what kind of claim is this, and is it even a refund request
    2. route       which agents does this case actually need
    3. gates       is the evidence legible; what is the seller's posture
    4. confidence  auto-resolve, or put it in front of a person

Every call records its backend, its latency and its full probability
distribution on the case timeline, so the trace shows what decided and how
sure it was. That is the part an LLM logprob cannot give you.
"""

from __future__ import annotations

from refundry.config import settings
from refundry.jev import Choice, Noul, jev
from refundry.models import CaseState

CLAIM_TYPES = {
    "damaged": "Item arrived broken cracked smashed or damaged in transit, "
               "packaging crushed, physical harm to the goods",
    "not_received": "Parcel never arrived, buyer did not get it, missing "
                    "package, nothing was handed over",
    "wrong_item": "A different product was sent, incorrect model, not the item "
                  "that was ordered",
    "quality": "Item works and matches its description but is disappointing, "
               "poor quality, not good enough",
}

SELLER_POSTURE = {
    "accepts": "Seller agrees to the full claim and will refund everything",
    "counters": "Seller offers a partial amount, a gesture, a percentage, a "
                "goodwill payment instead of the full sum",
    "disputes": "Seller rejects the claim outright and offers nothing",
}


def _record(state: CaseState, where: str, response) -> None:
    state.routing[where] = response.summary()
    state.log("jev", f"system_one.{where}", str(response.summary()),
              backend=response.backend,
              latency_ms=round(response.latency_ms, 2))


def triage(state: CaseState) -> None:
    """Insertion point 1: at the edge, before a single agent is woken."""
    # The narrowest brief the decision needs. Handing it the whole case would
    # let carrier metadata ("delivered") argue for the wrong label.
    brief = {"buyer_says": state.claim.narrative}
    r = jev.system_one(brief, {
        "claim_type": Choice("What kind of refund claim is this", CLAIM_TYPES),
        "is_refund_request": Noul(
            "The buyer wants money back, a refund, a return or compensation"),
    })
    _record(state, "intake", r)
    choice = r.choices["claim_type"]
    state.claim_type = choice.choice  # type: ignore[assignment]
    state.routing["intake_confidence"] = choice.confidence


def route(state: CaseState) -> None:
    """Insertion point 2: which agents this case actually needs.

    Today the naive orchestrator fans out to all four, every time. These two
    decisions are what let it stop doing that.
    """
    state.needs_evidence = bool(state.claim.evidence_refs)
    state.needs_seller = bool(state.order and state.order.seller_is_third_party)
    state.routing["route"] = {
        "needs_evidence": state.needs_evidence,
        "needs_seller": state.needs_seller,
        "why": "evidence attached" if state.needs_evidence else "no evidence attached",
    }
    state.log("jev", "route",
              f"evidence={state.needs_evidence} seller={state.needs_seller}")


def seller_posture(state: CaseState, message: str) -> str:
    """Insertion point 3: a gate. Three labels, not an essay."""
    r = jev.system_one({"seller_said": message},
                       {"posture": Choice("How did the seller's agent respond",
                                          SELLER_POSTURE)})
    _record(state, "seller_posture", r)
    return r.choices["posture"].choice


DAMAGE_ORIGIN = {
    "transit": "Outer carton crushed dented or torn, foam insert damaged, "
               "fracture edges bright and clean with no wear, packaging harmed "
               "at the same corner as the item",
    "use": "Scale limescale discolouration staining or wear on the part, "
           "consistent with the item having been used before it broke",
    "unclear": "Photographs do not show the failure or the packaging well "
               "enough to tell which",
}


def damage_origin(state: CaseState, observations: list[str]) -> tuple[str, float]:
    """Insertion point 3: a gate, and a real judgement call.

    Whether a crack came from transit or from use is exactly the kind of
    bounded question a System One model is for -- three labels, known in
    advance, and an answer a switch statement can consume. Note that it does
    NOT decide legibility: the service already knows whether a file parsed,
    and a model should not second-guess a fact.
    """
    r = jev.system_one({"observations": observations},
                       {"origin": Choice("What does the damage pattern indicate",
                                         DAMAGE_ORIGIN)})
    _record(state, "damage_origin", r)
    pick = r.choices["origin"]
    return pick.choice, pick.confidence


def confidence_gate(state: CaseState) -> tuple[bool, float, str]:
    """Insertion point 4, and the one worth having.

    Returns (auto_ok, confidence, why). A calibrated probability decides whether
    the case can resolve on the amount rule alone, or whether a person should
    see it regardless of the amount.
    """
    facts = {
        "claim_type": state.claim_type,
        "policy": state.verdict.reasoning if state.verdict else "",
        "governing_clause": state.verdict.governing_clause if state.verdict else "",
        "evidence": state.evidence.summary if state.evidence else "",
        "abuse": state.abuse.explain() if state.abuse else "",
        "seller": state.seller.message if state.seller else "",
    }
    r = jev.system_one(facts, {
        "clear_cut": Noul("The claim is clearly covered, the evidence supports "
                          "it, the seller agrees and the risk is low"),
    })
    _record(state, "confidence_gate", r)
    conf = r.nouls["clear_cut"].noul
    floor = settings.confidence_floor

    if state.abuse and state.abuse.recommends_manual_review:
        return False, conf, "risk recommends manual review"
    if conf < floor:
        return False, conf, f"confidence {conf:.2f} is below the {floor:.2f} floor"
    return True, conf, f"confidence {conf:.2f} clears the {floor:.2f} floor"
