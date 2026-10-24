"""Google ADK engine.

Runs the shared node registry as a real ADK workflow: a custom
``BaseAgent`` whose ``_run_async_impl`` walks the graph's nodes and edges,
driven by the ADK ``Runner`` and backed by an ADK session service. Each node
transition is emitted as an ADK ``Event``, so the traversal is a first-class
ADK invocation rather than a hand-rolled loop.

The node functions are identical to the other engines, so the refund outcome is
the same. Durability (checkpoints) and the approval interrupt/resume use
``store``, exactly like the deterministic and LangGraph engines.
"""

from __future__ import annotations

from refundry.agents.arbiter.engines.base import Engine
from refundry.agents.arbiter.graph_engine import END, Interrupt, RunResult, _dump


class ADKEngine(Engine):
    key = "google_adk"
    label = "Google ADK"

    async def run(self, state, *, thread_id: str, start: str | None = None,
                  resume: dict | None = None, max_steps: int = 40) -> RunResult:
        from google.adk.agents import BaseAgent
        from google.adk.events import Event
        from google.adk.runners import InMemoryRunner
        from google.genai import types

        graph = self.graph
        entry = start or graph.start
        holder: dict = {}

        class RefundryWorkflowAgent(BaseAgent):
            """An ADK agent whose body is the Arbiter's node/edge graph."""

            async def _run_async_impl(self, ctx):
                current = entry
                rsm = resume
                visited: list[str] = []
                steps = 0

                while current != END:
                    if steps >= max_steps:
                        holder["result"] = RunResult(
                            "failed", state, node=current, visited=visited)
                        return
                    steps += 1
                    fn = graph.nodes.get(current)
                    if fn is None:
                        holder["result"] = RunResult(
                            "failed", state, node=current, visited=visited)
                        return

                    visited.append(current)
                    try:
                        # `resume` is consumed by the first node after a pause.
                        nxt = await fn(state, rsm)
                        rsm = None
                    except Interrupt as it:
                        store_checkpoint(thread_id, current, state)
                        holder["result"] = RunResult(
                            "input-required", state, payload=it.payload,
                            node=current, visited=visited)
                        yield Event(author=self.name,
                                    custom_metadata={"node": current,
                                                     "status": "input-required"})
                        return

                    nxt = nxt or END
                    store_checkpoint(thread_id, nxt, state)
                    yield Event(author=self.name,
                                custom_metadata={"node": current, "next": nxt})
                    current = nxt

                holder["result"] = RunResult(
                    "completed", state, node=END, visited=visited)

        agent = RefundryWorkflowAgent(name="refundry_workflow")
        runner = InMemoryRunner(agent=agent, app_name="refundry")
        await runner.session_service.create_session(
            app_name="refundry", user_id="arbiter", session_id=thread_id)

        message = types.Content(role="user",
                                parts=[types.Part(text="resolve_refund")])
        async for _event in runner.run_async(
                user_id="arbiter", session_id=thread_id, new_message=message):
            pass

        return holder.get("result") or RunResult(
            "failed", state, node=entry, visited=[])


def store_checkpoint(thread_id: str, node: str, state) -> None:
    from refundry import store

    store.save_checkpoint(thread_id, node, _dump(state))
