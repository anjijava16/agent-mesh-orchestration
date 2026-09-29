"""Witness's service. Decides which files parsed and what they contain."""

from __future__ import annotations

from refundry.agents._base import client
from refundry.mcp import MCPCallError
from refundry.models import EvidenceReport, Fact

TRANSIT_WORDS = ("crush", "crushed", "torn", "fracture", "impact", "dent",
                 "damaged", "seam")
FRESH_WORDS = ("bright", "clean", "no discolouration", "no scale")


async def extract(evidence_refs: list[str], *,
                  context_id: str = "") -> tuple[EvidenceReport, list[str]]:
    docs = client("documents", caller="witness")
    facts: list[Fact] = []
    legible_all = True
    quarantined: list[str] = []

    for ref in evidence_refs:
        try:
            parsed = await docs.call("parse_document", ref=ref)
        except MCPCallError as exc:
            facts.append(Fact(source_ref=ref, kind="error",
                              statement=str(exc), confidence=0.0))
            legible_all = False
            continue

        if not parsed.get("legible", False):
            legible_all = False

        check = parsed.get("injection_check") or {}
        if check.get("quarantined"):
            # Reported as a finding about the document, never forwarded as text.
            quarantined.append(ref)
            facts.append(Fact(
                source_ref=ref, kind="security",
                statement="document contains embedded text addressed to an agent; "
                          "quarantined at the documents server and not interpreted",
                confidence=1.0,
            ))

        for obs in parsed.get("observations", []):
            facts.append(Fact(source_ref=ref, kind=parsed.get("kind", "document"),
                              statement=obs, confidence=0.88))

    blob = " ".join(f.statement.lower() for f in facts if f.kind != "security")
    transit = any(w in blob for w in TRANSIT_WORDS) or None
    serial = None
    if "serial" in blob:
        serial = "matches" in blob

    report = EvidenceReport(
        facts=facts,
        legible=legible_all,
        damage_consistent_with_transit=transit,
        serial_matches_shipment=serial,
    )
    return report, quarantined
