"""Crestline Home's A2A lifecycle.

Deliberately slower than the internal agents, because the thing that actually
dominates the wall clock in this system is the hop that leaves the building.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI

from refundry.a2a import A2AServer, Executor, RequestContext
from refundry.agents.counterparty import agent, service
from refundry.agents.counterparty.card import CARD

# Seconds of simulated external latency. Set to 0 for tests.
DELAY = float(os.getenv("REFUNDRY_SELLER_DELAY", "0.4"))


class CounterpartyExecutor(Executor):
    skill = "respond_to_claim"

    async def execute(self, ctx: RequestContext) -> None:
        d = ctx.data
        ctx.working("reviewing the claim against our despatch record")
        if DELAY:
            await asyncio.sleep(DELAY)

        response = service.respond(
            order_total=float(d.get("order_total", 0.0)),
            claim_type=d.get("claim_type", "unknown"),
            hard_constraint=d.get("hard_constraint", ""),
            evidence_summary=d.get("evidence_summary", ""),
        )
        text = await agent.phrase(response)
        ctx.artifact("seller_response", response.model_dump(mode="json"), text=text)
        ctx.complete(text)


def app() -> FastAPI:
    return A2AServer(CARD, CounterpartyExecutor(), agent_key="counterparty").app()
