"""Sentry's model half: whether a high score is a buyer signal or a seller one.

The service already did the arithmetic. This writes the sentence that makes the
number defensible to the person who has to act on it.
"""

from __future__ import annotations

from refundry.agents._base import judge
from refundry.models import AbuseScore


def _deterministic(s: AbuseScore) -> str:
    head = f"Abuse score {s.score:.2f} ({s.band})."
    if s.recommends_manual_review:
        head += " Recommends manual review."
    else:
        head += " Does not on its own warrant manual review."
    return head + " " + "; ".join(s.drivers) + "."


async def explain(s: AbuseScore, *, context_id: str = "") -> str:
    return await judge("sentry", lambda: None, fallback=_deterministic(s),
                       context_id=context_id)
