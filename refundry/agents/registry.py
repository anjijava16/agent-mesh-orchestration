"""Every A2A agent, by key. `build(key)` returns its FastAPI app.

In a real estate this is the discovery allow-list: an agent that is not in here
is unreachable, not merely untrusted.
"""

from __future__ import annotations

from fastapi import FastAPI

AGENTS = ["arbiter", "tracer", "witness", "statute", "sentry", "treasury",
          "counterparty"]

# The agents the orchestrator may delegate to, and the skill it calls on each.
SKILLS = {
    "tracer": "trace_order",
    "witness": "extract_evidence",
    "statute": "assess_eligibility",
    "sentry": "score_abuse",
    "treasury": "disburse",
    "counterparty": "respond_to_claim",
}


def build(key: str) -> FastAPI:
    module = __import__(f"refundry.agents.{key}.executor", fromlist=["app"])
    return module.app()
