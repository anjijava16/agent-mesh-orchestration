"""Statute's A2A lifecycle."""

from __future__ import annotations

from fastapi import FastAPI

from refundry.a2a import A2AServer, Executor, RequestContext
from refundry.agents._base import client
from refundry.agents.statute import agent, service
from refundry.agents.statute.card import CARD


class StatuteExecutor(Executor):
    skill = "assess_eligibility"

    async def execute(self, ctx: RequestContext) -> None:
        d = ctx.data
        claim_type = d.get("claim_type", "unknown")
        order_total = float(d.get("order_total", 0.0))
        seller_ref = d.get("seller_ref", "")

        ctx.working(f"assessing a {claim_type} claim against the policy book")
        verdict, evaluations = await service.assess(
            claim_type=claim_type,
            order_total=order_total,
            days_since_delivery=d.get("days_since_delivery"),
            seller_ref=seller_ref,
            context_id=ctx.context_id,
        )

        seller_name = seller_ref
        try:
            seller = await client("catalog", caller="statute").call(
                "get_seller_policy", seller_ref=seller_ref)
            seller_name = seller.get("display_name", seller_ref)
        except Exception:
            pass

        verdict.reasoning = await agent.explain(verdict, seller_name,
                                                context_id=ctx.context_id)
        ctx.artifact("verdict", verdict.model_dump(mode="json"),
                     text=verdict.reasoning)
        ctx.artifact("evaluations", {"evaluations": evaluations})
        ctx.complete(verdict.reasoning)


def app() -> FastAPI:
    return A2AServer(CARD, StatuteExecutor(), agent_key="statute").app()
