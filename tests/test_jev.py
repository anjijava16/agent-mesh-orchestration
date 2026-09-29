"""The System One layer.

These test the LOCAL stand-in, which is not Jev. What they pin down is the
contract the architecture depends on: a label from a declared set, a
probability distribution over all of them, and a confidence to gate on.
"""

import pytest

from refundry.jev import JevClient, Noul, Score

NARRATIVE = ("It arrived with the boiler casing cracked. The seller is telling "
             "me to pay return shipping on a machine that showed up broken.")

CLAIM_TYPES = {
    "damaged": "Item arrived broken cracked smashed or damaged in transit",
    "not_received": "Parcel never arrived, buyer did not get it, missing package",
    "wrong_item": "A different product was sent, incorrect model",
    "quality": "Item works and matches its description but is disappointing",
}


@pytest.fixture
def jev():
    return JevClient(mode="local")


def test_a_choice_can_only_return_a_declared_label(jev):
    """The property that makes it type-safe: the answer is from the set, always."""
    r = jev.choose({"buyer_says": NARRATIVE}, "what kind of claim", CLAIM_TYPES)
    assert r.choice in CLAIM_TYPES


def test_probabilities_cover_every_label_and_sum_to_one(jev):
    r = jev.choose({"buyer_says": NARRATIVE}, "what kind of claim", CLAIM_TYPES)
    assert set(r.probabilities) == set(CLAIM_TYPES)
    assert abs(sum(r.probabilities.values()) - 1.0) < 1e-6


def test_it_reads_the_narrative_correctly(jev):
    r = jev.choose({"buyer_says": NARRATIVE}, "what kind of claim", CLAIM_TYPES)
    assert r.choice == "damaged"
    assert r.probabilities["damaged"] > r.probabilities["not_received"]


def test_an_empty_state_does_not_invent_a_winner(jev):
    """No signal must produce a flat distribution AND a near-zero confidence.

    This is the property the gate depends on: an unanswerable question has to
    come back visibly unsure, not merely arbitrary.
    """
    r = jev.choose({}, "what kind of claim", CLAIM_TYPES)
    assert len(set(round(p, 6) for p in r.probabilities.values())) == 1
    assert r.confidence < 0.1


def test_confidence_tracks_the_margin_not_the_top_probability(jev):
    """A two-horse race is not confident, whatever the leader's share says."""
    clear = jev.choose({"buyer_says": NARRATIVE}, "q", CLAIM_TYPES)
    murky = jev.choose({"buyer_says": "it arrived"}, "q", CLAIM_TYPES)
    assert clear.confidence > murky.confidence


def test_it_is_deterministic(jev):
    a = jev.choose({"buyer_says": NARRATIVE}, "q", CLAIM_TYPES)
    b = jev.choose({"buyer_says": NARRATIVE}, "q", CLAIM_TYPES)
    assert a.choice == b.choice and a.probabilities == b.probabilities


def test_score_returns_a_level_on_the_declared_ladder(jev):
    r = jev.system_one({"text": "very angry, this is unacceptable"}, {
        "frustration": Score("how frustrated", ["calm just stating facts",
                                                "frustrated but civil",
                                                "very angry strong language"])})
    s = r.scores["frustration"]
    assert 0 <= s.score <= 2
    assert len(s.legend) == 3


def test_noul_is_a_probability(jev):
    p = jev.likely({"text": "I want my money back"},
                   "the buyer wants money back or a refund")
    assert 0.0 <= p <= 1.0


def test_backend_is_always_reported(jev):
    r = jev.system_one({"x": "y"}, {"q": Noul("anything")})
    assert r.backend == "local", "a caller must always know which model answered"


def test_nested_state_is_flattened(jev):
    r = jev.choose({"claim": {"narrative": NARRATIVE}, "photos": ["cracked casing"]},
                   "what kind of claim", CLAIM_TYPES)
    assert r.choice == "damaged"
