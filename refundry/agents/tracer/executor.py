"""Tracer's A2A lifecycle, written out in full."""

from __future__ import annotations

from fastapi import FastAPI

from refundry.a2a import A2AServer, Executor, RequestContext
from refundry.agents.tracer import agent, service
from refundry.agents.tracer.card import CARD


class TracerExecutor(Executor):
    skill = "trace_order"

    async def execute(self, ctx: RequestContext) -> None:
        order_ref = ctx.data.get("order_ref")
        if not order_ref:
            ctx.reject("trace_order needs an order_ref")
            return

        ctx.working(f"tracing {order_ref}")
        facts = await service.trace(order_ref, context_id=ctx.context_id)
        summary = await agent.summarise(facts, context_id=ctx.context_id)

        ctx.artifact("order_facts", facts.model_dump(mode="json"), text=summary)
        ctx.complete(summary)


def app() -> FastAPI:
    return A2AServer(CARD, TracerExecutor(), agent_key="tracer").app()
