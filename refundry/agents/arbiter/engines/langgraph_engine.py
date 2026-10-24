"""LangGraph engine.

Builds a real ``langgraph.graph.StateGraph`` from the shared node registry and
executes it with LangGraph's Pregel runtime. The node functions are the same
ones the deterministic engine runs, so the refund outcome is identical.

How the project's semantics map onto LangGraph:

  dynamic routing   each node returns the next node name; the wrapper emits a
                    ``Command(goto=...)`` so LangGraph routes dynamically
  arbitrary start   a conditional edge from ``START`` reads ``_start`` from the
                    initial state, so a resumed case can begin mid-graph
  the approval pause a node raises ``Interrupt``; the wrapper catches it,
                    checkpoints to ``store`` and routes to ``END`` carrying the
                    interrupt payload out

No LangGraph checkpointer is attached: durability lives in ``store`` (the same
place the other engines use), so a resume works regardless of which engine
started the case.
"""

from __future__ import annotations

from typing import Any, TypedDict

from refundry import store
from refundry.agents.arbiter.engines.base import Engine
from refundry.agents.arbiter.graph_engine import END, Interrupt, RunResult, _dump


class _Chan(TypedDict, total=False):
    case: Any           # the live CaseState object, carried by reference
    _start: str
    _resume: dict | None
    _resumed: bool
    _thread: str
    _visited: list
    _steps: int
    _interrupt: dict | None
    _last: str


class LangGraphEngine(Engine):
    key = "langgraph"
    label = "LangGraph"

    def __init__(self, graph):
        super().__init__(graph)
        self._compiled = None

    def _build(self):
        from langgraph.graph import END as LG_END
        from langgraph.graph import START, StateGraph
        from langgraph.types import Command

        nodes = self.graph.nodes

        def make(name, fn):
            async def wrapper(s: _Chan):
                state = s["case"]
                visited = list(s.get("_visited", [])) + [name]
                steps = s.get("_steps", 0) + 1
                thread = s.get("_thread", "")
                # The resume payload is consumed only by the first node that
                # runs after a pause, which is the start node.
                resume = (s.get("_resume")
                          if name == s.get("_start") and not s.get("_resumed")
                          else None)
                try:
                    nxt = await fn(state, resume)
                except Interrupt as it:
                    store.save_checkpoint(thread, name, _dump(state))
                    return Command(goto=LG_END, update={
                        "case": state, "_interrupt": it.payload, "_last": name,
                        "_visited": visited, "_steps": steps,
                        "_resume": None, "_resumed": True})

                nxt = nxt or END
                store.save_checkpoint(thread, nxt, _dump(state))
                goto = LG_END if nxt == END else nxt
                return Command(goto=goto, update={
                    "case": state, "_last": nxt, "_visited": visited,
                    "_steps": steps, "_resume": None, "_resumed": True})

            return wrapper

        sg = StateGraph(_Chan)
        for nm, fn in nodes.items():
            sg.add_node(nm, make(nm, fn))
        sg.add_conditional_edges(
            START,
            lambda s: s.get("_start") or self.graph.start,
            {nm: nm for nm in nodes},
        )
        return sg.compile()

    async def run(self, state, *, thread_id: str, start: str | None = None,
                  resume: dict | None = None, max_steps: int = 40) -> RunResult:
        if self._compiled is None:
            self._compiled = self._build()

        entry = start or self.graph.start
        init: _Chan = {
            "case": state, "_start": entry, "_resume": resume,
            "_thread": thread_id, "_visited": [], "_steps": 0,
        }
        try:
            final = await self._compiled.ainvoke(
                init, config={"recursion_limit": max_steps})
        except Exception:
            # A recursion-limit hit or an unexpected node failure.
            return RunResult("failed", state, node=entry, visited=[])

        st = final.get("case", state)
        visited = final.get("_visited", [])
        if final.get("_interrupt"):
            return RunResult("input-required", st, payload=final["_interrupt"],
                             node=final.get("_last", ""), visited=visited)
        return RunResult("completed", st, node=END, visited=visited)
