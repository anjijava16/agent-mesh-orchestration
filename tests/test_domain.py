"""The decisions that must not depend on a model."""

from fastapi.testclient import TestClient

from refundry import ids, store
from refundry.agents.statute import rules
from refundry.agents.treasury import service as treasury
from refundry.servers import build

CLAUSE_014 = {
    "clause_id": "MKT-014", "title": "Damaged on arrival", "text": "...",
    "rule": {"applies_to": ["damaged"], "window_days": 30,
             "buyer_owes_shipping": False, "overrides_seller_policy": True,
             "refund_fraction": 1.0},
}
CLAUSE_044 = {
    "clause_id": "MKT-044", "title": "Quality", "text": "...",
    "rule": {"applies_to": ["quality"], "window_days": 30,
             "buyer_owes_shipping": True, "overrides_seller_policy": False,
             "refund_fraction": 0.85},
}


# -- the ruling ------------------------------------------------------------


def test_damaged_claim_is_covered_in_full():
    e = rules.evaluate(CLAUSE_014, claim_type="damaged",
                       days_since_delivery=9, order_total=1284.00)
    assert e["applies"] and e["within_window"]
    assert e["entitled_amount"] == 1284.00
    assert e["buyer_owes_shipping"] is False


def test_out_of_window_is_not_covered():
    e = rules.evaluate(CLAUSE_014, claim_type="damaged",
                       days_since_delivery=45, order_total=1284.00)
    assert e["applies"] and not e["within_window"]
    assert e["entitled_amount"] == 0.0


def test_quality_claim_keeps_the_restocking_fee():
    e = rules.evaluate(CLAUSE_044, claim_type="quality",
                       days_since_delivery=9, order_total=1000.00)
    assert e["entitled_amount"] == 850.00
    assert e["buyer_owes_shipping"] is True


def test_a_clause_that_overrides_the_seller_wins():
    chosen = rules.pick_governing([
        rules.evaluate(CLAUSE_044, claim_type="damaged",
                       days_since_delivery=9, order_total=100.0),
        rules.evaluate(CLAUSE_014, claim_type="damaged",
                       days_since_delivery=9, order_total=100.0),
    ])
    assert chosen["clause_id"] == "MKT-014"


# -- money -----------------------------------------------------------------


def test_the_guarantee_sets_the_floor_a_seller_offer_does_not_reduce_it():
    d = treasury.draft(case_id="RFD-1", entitled_amount=1284.00, tender="card",
                       citations=[{"clause_id": "MKT-014", "title": "t", "quote": "q"}],
                       seller_offer=513.60)
    assert d.amount == 1284.00
    assert "floor" in d.rationale


def test_threshold_decides_whether_a_signature_is_needed():
    assert treasury.needs_signature(1284.00) is True
    assert treasury.needs_signature(42.00) is False


def test_idempotency_key_is_derived_not_random():
    assert ids.idempotency_key("RFD-1", 10.0) == ids.idempotency_key("RFD-1", 10.0)
    assert ids.idempotency_key("RFD-1", 10.0) != ids.idempotency_key("RFD-1", 10.01)


def test_approval_claim_is_bound_to_case_amount_and_approver():
    base = ids.approval_claim("RFD-1", 100.0, "a@b")
    assert base != ids.approval_claim("RFD-1", 200.0, "a@b"), "amount must bind"
    assert base != ids.approval_claim("RFD-2", 100.0, "a@b"), "case must bind"
    assert base != ids.approval_claim("RFD-1", 100.0, "c@d"), "approver must bind"


# -- the payments server, which is the one that matters --------------------


def call(client, tool, args, **headers):
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1,
                                     "method": "tools/call",
                                     "params": {"name": tool, "arguments": args}},
                       headers=headers).json()["result"]


def test_no_refund_above_the_threshold_without_a_named_approver():
    c = TestClient(build("payments"))
    key = ids.idempotency_key("RFD-1", 1284.00)
    out = call(c, "issue_refund", {"case_id": "RFD-1", "amount": 1284.00,
                                   "tender": "card", "idempotency_key": key},
               **{"x-idempotency-key": key})
    assert out["isError"]
    assert "named approver" in out["content"][0]["text"]


def test_a_claim_minted_for_another_amount_does_not_authorise_this_one():
    c = TestClient(build("payments"))
    key = ids.idempotency_key("RFD-1", 1284.00)
    wrong = ids.approval_claim("RFD-1", 50.00, "a@b")   # minted for $50
    out = call(c, "issue_refund", {"case_id": "RFD-1", "amount": 1284.00,
                                   "tender": "card", "idempotency_key": key,
                                   "approver": "a@b", "approval_claim": wrong},
               **{"x-idempotency-key": key})
    assert out["isError"]
    assert "does not match" in out["content"][0]["text"]


def test_a_replayed_message_cannot_mint_a_second_refund():
    c = TestClient(build("payments"))
    key = ids.idempotency_key("RFD-1", 1284.00)
    claim = ids.approval_claim("RFD-1", 1284.00, "a@b")
    args = {"case_id": "RFD-1", "amount": 1284.00, "tender": "card",
            "idempotency_key": key, "approver": "a@b", "approval_claim": claim}
    first = call(c, "issue_refund", args, **{"x-idempotency-key": key})
    second = call(c, "issue_refund", args, **{"x-idempotency-key": key})
    assert first["structuredContent"]["replay"] is False
    assert second["structuredContent"]["replay"] is True
    assert len(store.ledger()) == 1, "exactly one row in the ledger"


def test_a_forged_idempotency_key_is_refused():
    c = TestClient(build("payments"))
    out = call(c, "issue_refund", {"case_id": "RFD-1", "amount": 10.0,
                                   "tender": "card", "idempotency_key": "idem-lol"},
               **{"x-idempotency-key": "idem-lol"})
    assert out["isError"]


# -- documents: untrusted input --------------------------------------------


def test_embedded_instructions_are_quarantined_not_returned_as_text():
    c = TestClient(build("documents"))
    out = call(c, "parse_document",
               {"ref": "case://RFD-48213/evidence/packing-slip.pdf"})
    body = out["structuredContent"]
    assert body["injection_check"]["quarantined"] is True
    # The instruction never appears among the observations the agent consumes.
    joined = " ".join(body["observations"]).lower()
    assert "ignore previous" not in joined
    assert "5,000" not in joined and "5000" not in joined


def test_redaction_runs_before_a_model_sees_anything():
    c = TestClient(build("documents"))
    out = call(c, "redact", {"text": "card 4111 1111 1111 1111 and a@b.com"})
    assert "[REDACTED-PAN]" in out["structuredContent"]["text"]
    assert "[REDACTED-EMAIL]" in out["structuredContent"]["text"]
