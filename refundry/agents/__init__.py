"""The six A2A agents.

Every one is the same five files, so once you have read one you can read any:

    card.py       what the agent advertises on its Agent Card
    service.py    the domain logic. Deterministic, no model, unit tested
    agent.py      the framework wiring, where a model would actually reason
    executor.py   the A2A lifecycle, written out in full
    __main__.py   puts it on a port

The rule that makes the split worth having:

    service.py DECIDES.  agent.py JUDGES AND EXPLAINS.

A model can have an opinion. It cannot produce an answer the service did not
sanction, and every model call degrades to the deterministic path on failure.
"""

from refundry.agents.registry import AGENTS, build

__all__ = ["AGENTS", "build"]
