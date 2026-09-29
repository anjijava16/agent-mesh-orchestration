"""Witness's A2A lifecycle."""

from __future__ import annotations

from fastapi import FastAPI

from refundry.a2a import A2AServer, Executor, RequestContext
from refundry.agents.witness import agent, service
from refundry.agents.witness.card import CARD


class WitnessExecutor(Executor):
    skill = "extract_evidence"

    async def execute(self, ctx: RequestContext) -> None:
        refs = ctx.data.get("evidence_refs") or []
        if not refs:
            ctx.artifact("evidence", {"facts": [], "legible": False,
                                      "damage_consistent_with_transit": None,
                                      "serial_matches_shipment": None,
                                      "summary": "no evidence supplied"})
            ctx.complete("No evidence was attached to this claim.")
            return

        ctx.working(f"parsing {len(refs)} item(s) of evidence")
        report, quarantined = await service.extract(refs, context_id=ctx.context_id)
        report.summary = await agent.assess(report, context_id=ctx.context_id)

        if quarantined:
            ctx.artifact("security", {"quarantined_refs": quarantined},
                         text=f"{len(quarantined)} document(s) contained embedded "
                              "instructions; quarantined, not interpreted")

        ctx.artifact("evidence", report.model_dump(mode="json"), text=report.summary)
        ctx.complete(report.summary)


def app() -> FastAPI:
    return A2AServer(CARD, WitnessExecutor(), agent_key="witness").app()
