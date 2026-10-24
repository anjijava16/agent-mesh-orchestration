"""Pluggable orchestrator engines.

The Arbiter's process is a graph of nodes and edges (see ``graph.py``). *What*
each node does is fixed and tested; *how* the graph is walked is an
implementation detail we can swap. Three engines drive the exact same node
registry, so the refund outcome is identical no matter which one runs:

  deterministic   the project's own ~90-line state-graph engine (jev:local)
  langgraph       a real LangGraph ``StateGraph`` with dynamic ``Command``
                  routing and a conditional entry point
  google_adk      a real Google ADK custom workflow agent driven by the ADK
                  ``Runner`` and session service

Every engine implements the same contract::

    async def run(state, *, thread_id, start=None, resume=None, max_steps=40)
        -> RunResult

Checkpointing and the approval interrupt/resume are handled identically across
all three (saved to ``store``), so a case started on one engine can even be
resumed on another.

The selected engine is persisted in SQLite (``store.get_orchestrator`` /
``store.set_orchestrator``). Postgres later changes nothing here.
"""

from __future__ import annotations

from refundry.agents.arbiter.engines.base import Engine

# -- registry --------------------------------------------------------------
# key -> (module, class name, human label). Imports are lazy so that the
# default path never imports LangGraph or ADK, keeping startup fast and the
# optional dependencies genuinely optional.
_REGISTRY: dict[str, tuple[str, str, str]] = {
    "deterministic": (
        "refundry.agents.arbiter.engines.deterministic",
        "DeterministicEngine",
        "deterministic · jev:local",
    ),
    "langgraph": (
        "refundry.agents.arbiter.engines.langgraph_engine",
        "LangGraphEngine",
        "LangGraph",
    ),
    "google_adk": (
        "refundry.agents.arbiter.engines.adk_engine",
        "ADKEngine",
        "Google ADK",
    ),
}

DEFAULT_ENGINE = "deterministic"

# Which optional package each engine needs, so the UI can show availability.
_REQUIRES: dict[str, str | None] = {
    "deterministic": None,
    "langgraph": "langgraph",
    "google_adk": "google.adk",
}


def _importable(module: str | None) -> bool:
    if not module:
        return True
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def available_engines() -> list[dict]:
    """Metadata for every engine, for the gateway/UI to render a selector."""
    out = []
    for key, (_mod, _cls, label) in _REGISTRY.items():
        out.append({
            "key": key,
            "label": label,
            "available": _importable(_REQUIRES.get(key)),
            "requires": _REQUIRES.get(key),
        })
    return out


def is_available(key: str) -> bool:
    return key in _REGISTRY and _importable(_REQUIRES.get(key))


def get_engine(key: str | None) -> Engine:
    """Build the selected engine, falling back to deterministic if the key is
    unknown or its optional dependency is not installed."""
    from refundry.agents.arbiter.graph import graph

    if not key or key not in _REGISTRY or not is_available(key):
        key = DEFAULT_ENGINE

    import importlib

    module, cls_name, label = _REGISTRY[key]
    cls = getattr(importlib.import_module(module), cls_name)
    engine = cls(graph)
    engine.key = key
    engine.label = label
    return engine


__all__ = [
    "Engine",
    "DEFAULT_ENGINE",
    "available_engines",
    "is_available",
    "get_engine",
]
