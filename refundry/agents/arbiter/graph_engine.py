"""A small, explicit state graph with durable checkpoints and interrupts.

Deliberately about ninety lines rather than a framework import, so that the two
properties the architecture actually depends on are visible:

  * the state is checkpointed after EVERY node, to Postgres-shaped storage, so
    a restart during a four-hour approval wait resumes at the node it stopped on
  * a node may raise an interrupt, which saves and returns rather than blocking

Swap this for LangGraph's StateGraph and nothing above it changes: the node
functions, the routing and the interrupt semantics are the same shape.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from refundry import store

END = "__end__"


class Interrupt(Exception):
    """Raised by a node that needs something a person has to supply."""

    def __init__(self, payload: dict):
        super().__init__("interrupt")
        self.payload = payload


@dataclass
class RunResult:
    status: str            # "completed" | "input-required" | "failed"
    state: Any
    payload: dict | None = None
    node: str = ""
    visited: list[str] | None = None


class Graph:
    def __init__(self, start: str):
        self.start = start
        self.nodes: dict[str, Callable[..., Awaitable[str]]] = {}

    def node(self, name: str):
        def deco(fn):
            self.nodes[name] = fn
            return fn
        return deco

    async def run(self, state, *, thread_id: str, start: str | None = None,
                  resume: dict | None = None, max_steps: int = 40) -> RunResult:
        current = start or self.start
        visited: list[str] = []
        steps = 0

        while current != END:
            if steps >= max_steps:
                return RunResult("failed", state, node=current, visited=visited)
            steps += 1
            fn = self.nodes.get(current)
            if fn is None:
                return RunResult("failed", state, node=current, visited=visited)

            visited.append(current)
            try:
                # `resume` is consumed by the first node that runs after a pause,
                # which is the node that raised the interrupt.
                nxt = await fn(state, resume)
                resume = None
            except Interrupt as it:
                store.save_checkpoint(thread_id, current, _dump(state))
                return RunResult("input-required", state, payload=it.payload,
                                 node=current, visited=visited)

            store.save_checkpoint(thread_id, nxt or END, _dump(state))
            current = nxt or END

        return RunResult("completed", state, node=END, visited=visited)


def _dump(state) -> dict:
    return state.model_dump(mode="json") if hasattr(state, "model_dump") else dict(state)
