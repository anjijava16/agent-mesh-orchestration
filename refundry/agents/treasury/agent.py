"""Treasury's model half: the reasoning an approver reads before deciding."""

from __future__ import annotations

from refundry.agents._base import judge
from refundry.models import Disbursement


def _deterministic(d: Disbursement, abuse_note: str) -> str:
    cite = d.citations[0] if d.citations else None
    lines = [f"Proposed: ${d.amount:,.2f} refund to {d.tender}."]
    if cite:
        lines.append(f"Basis: {cite.clause_id} {cite.title}.")
    if abuse_note:
        lines.append(f"Risk: {abuse_note}")
    lines.append(d.rationale)
    return " ".join(lines)


async def rationale(d: Disbursement, abuse_note: str = "", *,
                    context_id: str = "") -> str:
    return await judge("treasury", lambda: None,
                       fallback=_deterministic(d, abuse_note),
                       context_id=context_id)
