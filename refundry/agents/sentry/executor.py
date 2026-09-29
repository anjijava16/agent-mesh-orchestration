"""Sentry's A2A lifecycle."""

from __future__ import annotations

from fastapi import FastAPI

from refundry.a2a import A2AServer, Executor, RequestContext
from refundry.agents.sentry import agent, service
from refundry.agents.sentry.card import CARD


class SentryExecutor(Executor):
    skill = "score_abuse"

    async def execute(self, ctx: RequestContext) -> None:
        d = ctx.data
        buyer_ref = d.get("buyer_ref")
        if not buyer_ref:
            ctx.reject("score_abuse needs a buyer_ref")
            return

        with_evidence = d.get("evidence_supports_transit") is not None
        ctx.working("re-scoring with the evidence attached" if with_evidence
                    else "scoring the account")

        result = await service.score(
            buyer_ref=buyer_ref,
            seller_ref=d.get("seller_ref", ""),
            evidence_supports_transit=d.get("evidence_supports_transit"),
            seller_defect_signal=bool(d.get("seller_defect_signal")),
            context_id=ctx.context_id,
        )
        result.explanation = await agent.explain(result, context_id=ctx.context_id)

        ctx.artifact("abuse_score", result.model_dump(mode="json"),
                     text=result.explanation)
        ctx.complete(result.explanation)


def app() -> FastAPI:
    return A2AServer(CARD, SentryExecutor(), agent_key="sentry").app()
