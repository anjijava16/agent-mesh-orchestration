"""End to end, against the running network.

    make run          in one terminal
    make test         in another

Skipped automatically when the gateway is not up, so the unit suite stays
runnable with nothing started.
"""

import httpx
import pytest

from refundry import ids
from refundry.config import base_url

GW = base_url("gateway") + "/api/v1"

CLAIM = {
    "order_ref": "NW-7731094",
    "buyer_ref": "BUY-90211",
    "narrative": ("It arrived with the boiler casing cracked. The seller is "
                  "telling me to pay return shipping on a machine that showed "
                  "up broken."),
    "evidence_refs": [
        "case://RFD-48213/evidence/photo-1.jpg",
        "case://RFD-48213/evidence/photo-2.jpg",
        "case://RFD-48213/evidence/photo-3.jpg",
        "case://RFD-48213/evidence/packing-slip.pdf",
    ],
}


def _up() -> bool:
    try:
        return httpx.get(f"{GW}/health", timeout=2).status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not _up(), reason="network not running; make run"),
]


@pytest.fixture(scope="module")
def resolved():
    """File the claim, approve it, and hand both responses to the tests."""
    with httpx.Client(timeout=180) as c:
        filed = c.post(f"{GW}/refunds", json=CLAIM).json()
        approved = None
        if filed["awaiting_approval"]:
            approved = c.post(
                f"{GW}/refunds/{filed['case_id']}/approve",
                json={"approved": True,
                      "approver": "elena.marchetti@northwind"}).json()
        return filed, approved


def test_all_fifteen_services_are_reachable():
    d = httpx.get(f"{GW}/doctor", timeout=20).json()
    assert d["ok"], [c for c in d["checks"] if not c["ok"]]
    assert len(d["checks"]) == 14  # 7 agents + 7 MCP servers


def test_every_agent_card_is_discoverable_and_signed():
    agents = httpx.get(f"{GW}/agents", timeout=20).json()["agents"]
    assert all(a["reachable"] for a in agents)
    assert all(a["signature"] for a in agents)
    seller = next(a for a in agents if a["key"] == "counterparty")
    assert seller["organization"] == "Crestline Home", "the seller is not ours"


def test_every_mcp_server_is_stateless():
    servers = httpx.get(f"{GW}/servers", timeout=20).json()["servers"]
    assert all(s["reachable"] and s["stateless"] for s in servers)
    pay = next(s for s in servers if s["key"] == "payments")
    assert pay["riskTier"] == "high"


def test_the_claim_pauses_for_a_signature(resolved):
    filed, _ = resolved
    assert filed["case_id"] == "RFD-48213"
    assert filed["awaiting_approval"] is True
    assert filed["approval_request"]["amount"] == 1284.00


def test_jev_classified_the_claim_before_any_agent_ran(resolved):
    filed, _ = resolved
    intake = filed["routing"]["intake"]
    assert intake["choices"]["claim_type"]["choice"] == "damaged"
    assert filed["claim_type"] == "damaged"


def test_the_approval_request_carries_a_citation_and_a_risk_note(resolved):
    """A decision without citations does not render an approve button."""
    filed, _ = resolved
    req = filed["approval_request"]
    assert req["citations"], "no citation means no approval"
    assert req["citations"][0]["clause_id"] == "MKT-014"
    assert req["abuse"]


def test_sentry_rescored_itself_when_re_asked_with_evidence(resolved):
    """The orchestrator did not overrule the score. It asked again, with more,
    and Sentry moved its own number."""
    filed, _ = resolved
    line = next(e for e in filed["timeline"] if e["event"] == "re-scored")
    before, after = line["detail"].split(" -> ")[0], line["detail"].split(" -> ")[1]
    assert float(before) > float(after.split()[0])


def test_the_seller_moved_when_re_asked_with_the_clause(resolved):
    filed, _ = resolved
    line = next(e for e in filed["timeline"] if e["event"] == "seller moved")
    assert "accepts" in line["detail"]


def test_the_guarantee_beat_the_sellers_partial_offer(resolved):
    _, approved = resolved
    assert approved["result"]["amount"] == 1284.00


def test_the_refund_posted_to_a_named_approver(resolved):
    _, approved = resolved
    assert approved["status"] == "resolved"
    assert approved["result"]["status"] == "posted"
    assert approved["result"]["approver"] == "elena.marchetti@northwind"


def test_the_injection_in_the_packing_slip_was_quarantined(resolved):
    filed, _ = resolved
    case = httpx.get(f"{GW}/refunds/{filed['case_id']}", timeout=20).json()
    witness = next(t for t in case["tasks"] if t.get("agent") == "witness")
    names = [a["name"] for a in witness["artifacts"]]
    assert "security" in names
    blob = str(witness["artifacts"]).lower()
    assert "5,000" not in blob and "pre-approved refund" not in blob


def test_one_context_id_threads_the_whole_case(resolved):
    filed, _ = resolved
    trail = httpx.get(f"{GW}/trail/{filed['case_id']}", timeout=20).json()["trail"]
    assert len(trail) > 40
    assert {r["context_id"] for r in trail} == {ids.context_id(filed["case_id"])}


def test_exactly_one_row_reached_the_ledger(resolved):
    rows = httpx.get(f"{GW}/ledger", timeout=20).json()["ledger"]
    assert len([r for r in rows if r["case_id"] == "RFD-48213"]) == 1


def test_approving_twice_does_not_mint_a_second_refund(resolved):
    """The task is terminal, so the second approval is refused outright."""
    filed, _ = resolved
    r = httpx.post(f"{GW}/refunds/{filed['case_id']}/approve",
                   json={"approved": True, "approver": "elena.marchetti@northwind"},
                   timeout=30)
    assert r.status_code == 409
    rows = httpx.get(f"{GW}/ledger", timeout=20).json()["ledger"]
    assert len([x for x in rows if x["case_id"] == "RFD-48213"]) == 1


def test_an_approval_without_a_named_approver_is_refused():
    r = httpx.post(f"{GW}/refunds/RFD-48213/approve",
                   json={"approved": True, "approver": ""}, timeout=30)
    assert r.status_code in (409, 422)
