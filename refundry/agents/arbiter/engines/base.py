"""The engine contract shared by every orchestrator."""

from __future__ import annotations

from refundry.agents.arbiter.graph_engine import Graph, RunResult


class Engine:
    """Walks a node/edge ``Graph`` to a terminal or an interrupt.

    Subclasses differ only in *how* they traverse the graph; the node
    functions, routing and interrupt/resume semantics are identical.
    """

    key: str = "base"
    label: str = "base"

    def __init__(self, graph: Graph):
        self.graph = graph

    async def run(self, state, *, thread_id: str, start: str | None = None,
                  resume: dict | None = None, max_steps: int = 40) -> RunResult:
        raise NotImplementedError
