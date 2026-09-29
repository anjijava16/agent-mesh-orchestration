"""Witness's model half: whether the damage reads as transit damage or use.

The service already decided what the files say. A model that describes a
photograph not in the case folder is discarded -- four lines, and a whole class
of failure disappears.
"""

from __future__ import annotations

from refundry.agents._base import judge
from refundry.models import EvidenceReport


def _deterministic(report: EvidenceReport) -> str:
    if not report.facts:
        return "No legible evidence was supplied."
    bits = []
    if report.damage_consistent_with_transit:
        bits.append("damage pattern is consistent with transit: the outer carton "
                    "is crushed at the same corner as the internal failure")
    if report.serial_matches_shipment:
        bits.append("the serial plate matches the unit on the shipment manifest, "
                    "so this is the item that was sent")
    if not bits:
        bits.append(f"{len(report.facts)} observations extracted")
    return ". ".join(b[0].upper() + b[1:] for b in bits) + "."


def _sanitise(text: str, report: EvidenceReport) -> str:
    """A model may only talk about evidence that is actually in the folder."""
    refs = {f.source_ref for f in report.facts}
    if any(tok.startswith("case://") and tok not in refs for tok in text.split()):
        return ""
    return text


async def assess(report: EvidenceReport, *, context_id: str = "") -> str:
    fallback = _deterministic(report)
    out = await judge("witness", lambda: None, fallback=fallback,
                      context_id=context_id)
    return _sanitise(out, report) or fallback
