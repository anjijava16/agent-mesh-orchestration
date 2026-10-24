"""The default engine: the project's own state-graph walker (jev:local)."""

from __future__ import annotations

from refundry.agents.arbiter.engines.base import Engine
from refundry.agents.arbiter.graph_engine import RunResult


class DeterministicEngine(Engine):
    key = "deterministic"
    label = "deterministic · jev:local"

    async def run(self, state, *, thread_id: str, start: str | None = None,
                  resume: dict | None = None, max_steps: int = 40) -> RunResult:
        return await self.graph.run(
            state, thread_id=thread_id, start=start, resume=resume,
            max_steps=max_steps)
