"""policy-kb -- the policy book.

Clauses carry two halves. `text` is prose, which is what gets quoted and what a
retrieval index would be built over. `rule` is a structured description of the
same clause, which is what actually gets evaluated.

Retrieval decides which clauses are worth EXPLAINING.
The structured rule decides which clauses are BROKEN.

A buyer is never denied, or waved through, because a model paraphrased a
paragraph.
"""

from __future__ import annotations

import json

from refundry.mcp import MCPServer, ToolError
from refundry.servers._seed import load

mcp = MCPServer("policy_kb", scope="policy.read", risk="low")


def _clauses() -> list[dict]:
    return load("policies")["clauses"]


@mcp.tool(read_only=True)
def search_policy(query: str, limit: int = 4) -> dict:
    """Find clauses whose prose bears on a query. Ranking only -- this decides
    what is worth explaining, not what is broken."""
    terms = {t for t in query.lower().split() if len(t) > 2}
    scored = []
    for c in _clauses():
        blob = f"{c['title']} {c['text']}".lower()
        hits = sum(1 for t in terms if t in blob)
        if hits:
            scored.append((hits, c))
    scored.sort(key=lambda p: -p[0])
    return {"query": query,
            "clauses": [c for _, c in scored[:limit]]}


@mcp.tool(read_only=True)
def get_clause(clause_id: str) -> dict:
    """One clause, both halves."""
    for c in _clauses():
        if c["clause_id"] == clause_id:
            return c
    raise ToolError(f"no clause {clause_id!r}; try search_policy first")


@mcp.tool(read_only=True)
def clauses_for(claim_type: str) -> dict:
    """Every clause whose structured rule applies to a claim type."""
    out = [c for c in _clauses() if claim_type in (c["rule"].get("applies_to") or [])]
    advisory = [c for c in _clauses() if c["rule"].get("advisory")]
    thresholds = [c for c in _clauses() if c["rule"].get("threshold")]
    return {"claim_type": claim_type, "governing": out,
            "advisory": advisory, "thresholds": thresholds}


for _c in load("policies")["clauses"]:
    def _make(clause=_c):
        def _read() -> str:
            return json.dumps(clause, indent=2)
        return _read
    mcp.resource(f"policy://marketplace/{_c['clause_id']}",
                 name=_c["title"])(_make())
