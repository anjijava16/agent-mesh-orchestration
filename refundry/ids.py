"""Identifiers. Deterministic where a replay must not mint a new one."""

from __future__ import annotations

import hashlib
import uuid


def new_uuid() -> str:
    return str(uuid.uuid4())


# The case the deck walks through, pinned so the demo output matches the slides.
PINNED = {"NW-7731094": "RFD-48213"}


def case_id(order_ref: str) -> str:
    """Stable per order, so filing the same claim twice finds the same case."""
    if order_ref in PINNED:
        return PINNED[order_ref]
    h = hashlib.sha256(order_ref.encode()).hexdigest()[:5].upper()
    return f"RFD-{int(h, 16) % 90000 + 10000}"


def context_id(case: str) -> str:
    return f"ctx-{case.lower()}"


def idempotency_key(case: str, amount: float) -> str:
    """The key `payments` requires. Derived, so a replayed A2A message cannot
    mint a second refund."""
    raw = f"{case}:{amount:.2f}".encode()
    return "idem-" + hashlib.sha256(raw).hexdigest()[:24]


def refund_ref(case: str, amount: float) -> str:
    raw = f"refund:{case}:{amount:.2f}".encode()
    return "REF-" + hashlib.sha256(raw).hexdigest()[:6].upper()


def approval_claim(case: str, amount: float, approver: str) -> str:
    """Bound to the case AND the amount AND the approver. Only the human review
    step can mint one, and it does not authorise a different amount."""
    raw = f"claim:{case}:{amount:.2f}:{approver}".encode()
    return "aprv-" + hashlib.sha256(raw).hexdigest()[:28]
