"""Treasury's A2A lifecycle -- including the pause.

The whole point of this file is `ctx.input_required`. Treasury does not call a
human. It moves its own task to input-required and returns, publishing the
numbers a person needs as an artifact. No worker is blocked, no connection is
held open, and the task keeps its id for as long as it takes.

When the approval arrives it is a message on the SAME task id, and the executor
runs again with the token present.
"""

from __future__ import annotations

from fastapi import FastAPI

from refundry.a2a import A2AServer, Executor, RequestContext, artifact_data
from refundry.agents.treasury import agent, service
from refundry.agents.treasury.card import CARD
from refundry.config import settings
from refundry.models import Disbursement


class TreasuryExecutor(Executor):
    skill = "disburse"

    async def execute(self, ctx: RequestContext) -> None:
        d = ctx.data

        # --- the resume path: an approval arrived on a task that was waiting
        if ctx.is_resume:
            if not d.get("approved"):
                ctx.artifact("result", {"status": "declined", "amount": 0.0,
                                        "message": "approver declined"})
                ctx.complete("Declined by the approver; no money moved.")
                return

            saved = artifact_data(ctx.task, "draft")
            if not saved:
                ctx.fail("resumed without a draft on the task")
                return
            disbursement = Disbursement(**saved)
            approver = d.get("approver", "")
            if not approver:
                ctx.input_required("approval arrived without a named approver")
                return

            result = await service.execute(
                case_id=d.get("case_id") or saved.get("case_id", ""),
                disbursement=disbursement,
                approver=approver,
                context_id=ctx.context_id,
            )
            ctx.artifact("result", result.model_dump(mode="json"))
            ctx.complete(result.message)
            return

        # --- the first pass
        case_id = d.get("case_id", "")
        ctx.working("drafting the disbursement")
        disbursement = service.draft(
            case_id=case_id,
            entitled_amount=float(d.get("entitled_amount", 0.0)),
            tender=d.get("tender", "card"),
            citations=d.get("citations") or [],
            seller_offer=float(d.get("seller_offer", 0.0)),
        )
        note = await agent.rationale(disbursement, d.get("abuse_note", ""),
                                     context_id=ctx.context_id)
        disbursement.rationale = note

        payload = disbursement.model_dump(mode="json")
        payload["case_id"] = case_id

        if disbursement.action == "decline":
            ctx.artifact("result", {"status": "declined", "amount": 0.0,
                                    "message": "no amount is payable on these facts"})
            ctx.complete("Nothing is payable on these facts.")
            return

        if service.needs_signature(disbursement.amount):
            # Publish the numbers a person needs, then stop.
            ctx.artifact("draft", payload, text=note)
            ctx.input_required(
                f"${disbursement.amount:,.2f} is at or above the "
                f"${settings.auto_approval_limit:,.2f} auto-approval threshold "
                f"and needs a named approver (MKT-060)")
            return

        result = await service.execute(case_id=case_id, disbursement=disbursement,
                                       context_id=ctx.context_id)
        ctx.artifact("draft", payload, text=note)
        ctx.artifact("result", result.model_dump(mode="json"))
        ctx.complete(result.message)


def app() -> FastAPI:
    return A2AServer(CARD, TreasuryExecutor(), agent_key="treasury").app()
