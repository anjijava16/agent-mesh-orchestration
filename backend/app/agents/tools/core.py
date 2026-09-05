"""Framework-neutral tool implementations.

Each tool is a plain async function with a typed signature and a docstring that
doubles as the model-facing description. The per-framework adapters in
`agents/tools/adapters.py` wrap these into LangChain tools, ADK FunctionTools or
Claude SDK MCP tools - the logic is never duplicated.
"""
from __future__ import annotations

import itertools
import json
import math
import re
import statistics
from contextvars import ContextVar
from typing import Any

from app.config import settings
from app.core.logging import get_logger
from app.core.resilience import tool_breaker, with_resilience
from app.llm.registry import get_embedder
from app.search.client import get_opensearch
from app.search.hybrid import hybrid_search

log = get_logger(__name__)

# Runtime-scoped context, set by the runtime before invoking a graph. Tools need
# the user id for tenant isolation but frameworks differ wildly in how they thread
# state, so we use a contextvar and keep the tool signatures clean.
tool_user_id: ContextVar[str] = ContextVar("tool_user_id", default="anonymous")
tool_document_ids: ContextVar[tuple[str, ...]] = ContextVar("tool_document_ids", default=())


async def hybrid_search_tool(query: str, top_k: int = 6) -> str:
    """Search the user's uploaded documents using hybrid BM25 + vector retrieval.

    Args:
        query: A focused retrieval query. Reformulate conversational phrasing into keywords.
        top_k: How many passages to return (1-20).

    Returns:
        JSON array of passages, each with content, filename, page and citation marker.
    """
    hits = await hybrid_search(
        query,
        embedder=get_embedder(),
        user_id=tool_user_id.get(),
        document_ids=list(tool_document_ids.get()) or None,
        top_k=max(1, min(top_k, 20)),
    )
    if not hits:
        return json.dumps({"passages": [], "note": "No matching passages in the corpus."})
    return json.dumps(
        {
            "passages": [
                {
                    "citation": f"[{h.citation()}]",
                    "filename": h.filename,
                    "page": h.page,
                    "content": h.content[:3000],
                    "score": round(h.score, 4),
                }
                for h in hits
            ]
        }
    )


async def corpus_overview_tool() -> str:
    """List what documents the user has ingested, with chunk counts. Use this before searching
    to know whether the corpus can answer the question at all."""
    client = get_opensearch()
    body = {
        "size": 0,
        "query": {"term": {"user_id": tool_user_id.get()}},
        "aggs": {"by_file": {"terms": {"field": "filename", "size": 100}}},
    }
    res = await client.search(index=settings.opensearch.documents_index, body=body)
    buckets = res.get("aggregations", {}).get("by_file", {}).get("buckets", [])
    return json.dumps({"documents": [{"filename": b["key"], "chunks": b["doc_count"]} for b in buckets]})


async def fetch_document_chunk_tool(document_id: str, chunk_index: int) -> str:
    """Fetch one specific chunk by document id and index. Use it to widen context around a
    hit that looks truncated."""
    client = get_opensearch()
    body = {
        "size": 3,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"document_id": document_id}},
                    {"term": {"user_id": tool_user_id.get()}},
                    {"range": {"chunk_index": {"gte": max(0, chunk_index - 1), "lte": chunk_index + 1}}},
                ]
            }
        },
        "sort": [{"chunk_index": "asc"}],
        "_source": {"excludes": ["embedding"]},
    }
    res = await client.search(index=settings.opensearch.documents_index, body=body)
    return json.dumps(
        [
            {"chunk_index": h["_source"]["chunk_index"], "content": h["_source"]["content"]}
            for h in res["hits"]["hits"]
        ]
    )


_ALLOWED_MATH = {k: v for k, v in vars(math).items() if not k.startswith("_")}
_ALLOWED_MATH.update({"abs": abs, "round": round, "min": min, "max": max, "sum": sum, "len": len})
_EXPR_RE = re.compile(r"^[0-9a-zA-Z_+\-*/%.,()\[\]\s^<>=!]+$")


async def calculator_tool(expression: str) -> str:
    """Evaluate a arithmetic expression precisely. Supports the Python math module
    (sqrt, log, pow, ...). Always use this instead of computing mentally.

    Args:
        expression: e.g. "(1240 - 987) / 987 * 100"
    """
    expr = expression.strip().replace("^", "**")
    if not _EXPR_RE.match(expr) or "__" in expr:
        return json.dumps({"error": "Expression contains unsupported characters."})
    try:
        value = eval(expr, {"__builtins__": {}}, _ALLOWED_MATH)
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    return json.dumps({"expression": expression, "result": value})


async def table_stats_tool(numbers: str, label: str = "series") -> str:
    """Summary statistics for a comma-separated list of numbers: count, sum, mean,
    median, stdev, min, max, and period-over-period deltas."""
    try:
        values = [float(x) for x in re.split(r"[,\s]+", numbers.strip()) if x]
    except ValueError:
        return json.dumps({"error": "Could not parse the series into numbers."})
    if not values:
        return json.dumps({"error": "Empty series."})
    deltas = [round(b - a, 6) for a, b in itertools.pairwise(values)]
    return json.dumps(
        {
            "label": label,
            "count": len(values),
            "sum": sum(values),
            "mean": statistics.fmean(values),
            "median": statistics.median(values),
            "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
            "min": min(values),
            "max": max(values),
            "deltas": deltas,
        }
    )


PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "us_ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
}


async def pii_scan_tool(text: str) -> str:
    """Scan text for personally identifiable information. Returns the categories found
    and a redacted rendering. Run this before any draft is shown to a user."""
    findings: dict[str, int] = {}
    redacted = text
    for name, pattern in PII_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            findings[name] = len(matches)
            redacted = pattern.sub(f"[REDACTED_{name.upper()}]", redacted)
    return json.dumps({"clean": not findings, "findings": findings, "redacted": redacted[:4000]})


POLICY_RULES: dict[str, str] = {
    "citations": "Every factual claim drawn from a document must carry a [filename p.N] citation.",
    "pii": "Customer PII must never appear verbatim in a generated answer; redact before display.",
    "financial_advice": "Do not present model output as personalised financial or legal advice.",
    "uncertainty": "Where evidence is absent or conflicting, state that plainly rather than hedging vaguely.",
    "retention": "Uploaded documents are retained for 90 days unless the user deletes them earlier.",
}


async def policy_lookup_tool(topic: str = "") -> str:
    """Look up the applicable content policy rules. Pass a topic to filter, or leave
    empty to get all of them."""
    if not topic:
        return json.dumps(POLICY_RULES)
    topic = topic.lower()
    hits = {k: v for k, v in POLICY_RULES.items() if topic in k or topic in v.lower()}
    return json.dumps(hits or POLICY_RULES)


@with_resilience(breaker=tool_breaker("web_search"), timeout=settings.resilience.tool_timeout_seconds,
                 label="tool.web_search")
async def _web_search(query: str, max_results: int) -> list[dict[str, Any]]:
    # Tavily is the reference implementation; swap the body for whichever
    # provider your org has a contract with.
    import os

    import httpx

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY not configured")
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": max_results, "search_depth": "advanced"},
        )
        res.raise_for_status()
        payload = res.json()
    return [
        {"title": r.get("title"), "url": r.get("url"), "content": (r.get("content") or "")[:1500]}
        for r in payload.get("results", [])
    ]


async def web_search_tool(query: str, max_results: int = 5) -> str:
    """Search the public web for current information. Use for anything that changes
    over time or is not in the user's documents."""
    try:
        results = await _web_search(query, max(1, min(max_results, 10)))
        return json.dumps({"results": results})
    except Exception as exc:
        log.warning("web_search_unavailable", error=str(exc)[:200])
        return json.dumps({"results": [], "error": "Web search is unavailable; answer from the corpus only."})


TOOL_REGISTRY: dict[str, Any] = {
    "hybrid_search": hybrid_search_tool,
    "corpus_overview": corpus_overview_tool,
    "fetch_document_chunk": fetch_document_chunk_tool,
    "calculator": calculator_tool,
    "table_stats": table_stats_tool,
    "pii_scan": pii_scan_tool,
    "policy_lookup": policy_lookup_tool,
    "web_search": web_search_tool,
}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "hybrid_search": {"query": str, "top_k": int},
    "corpus_overview": {},
    "fetch_document_chunk": {"document_id": str, "chunk_index": int},
    "calculator": {"expression": str},
    "table_stats": {"numbers": str, "label": str},
    "pii_scan": {"text": str},
    "policy_lookup": {"topic": str},
    "web_search": {"query": str, "max_results": int},
}


def get_tools(names: list[str]) -> dict[str, Any]:
    return {n: TOOL_REGISTRY[n] for n in names if n in TOOL_REGISTRY}
