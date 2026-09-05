"""The five specialist agents.

The same roster is instantiated by all four frameworks. Prompts live here, once,
so a wording change lands everywhere at the same time and a behavioural
regression is attributable to a single diff.

  orchestrator  - plans, routes, merges, owns the final answer
    |- researcher   - external/web + corpus discovery
    |- retriever    - hybrid RAG over the user's uploaded documents
    |- analyst      - numeric work, tabular reasoning, calculations
    |- compliance   - policy/PII/risk review of drafts
    |- writer       - final composition with citations
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentSpec:
    name: str
    display_name: str
    description: str
    instruction: str
    tools: list[str] = field(default_factory=list)
    output_key: str = ""


RESEARCHER = AgentSpec(
    name="researcher",
    display_name="Researcher",
    description="Finds and triages source material relevant to the request.",
    instruction=(
        "You are the Researcher. Your job is to find source material, not to answer the question.\n"
        "Use web_search for anything current or external, and corpus_overview to see what the user has "
        "already uploaded.\n"
        "Return a compact briefing: 3-8 bullet findings, each with its source. State plainly when you "
        "found nothing rather than filling the gap with plausible text. Never speculate about numbers."
    ),
    tools=["web_search", "corpus_overview"],
    output_key="research_findings",
)

RETRIEVER = AgentSpec(
    name="retriever",
    display_name="Retriever",
    description="Runs hybrid search over the user's document corpus and returns cited passages.",
    instruction=(
        "You are the Retriever. Call hybrid_search with a focused query - reformulate the user's wording "
        "into retrieval terms first. If the first pass is thin, try one alternative phrasing, then stop.\n"
        "Return the passages verbatim with their [filename p.N] markers attached. Do not summarise away "
        "the citation anchors; downstream agents depend on them."
    ),
    tools=["hybrid_search", "fetch_document_chunk"],
    output_key="retrieved_context",
)

ANALYST = AgentSpec(
    name="analyst",
    display_name="Analyst",
    description="Does the quantitative work: arithmetic, comparisons, table reasoning.",
    instruction=(
        "You are the Analyst. Any arithmetic goes through the calculator tool - never compute in your head, "
        "and never round silently.\n"
        "Work from the retrieved context and research findings. If a number you need is missing, say which "
        "number is missing and stop. A stated gap is worth more than a confident guess."
    ),
    tools=["calculator", "table_stats"],
    output_key="analysis",
)

COMPLIANCE = AgentSpec(
    name="compliance",
    display_name="Compliance Reviewer",
    description="Screens drafts for policy, PII and unsupported claims.",
    instruction=(
        "You are the Compliance Reviewer. Check the draft for: PII that should be redacted, claims with no "
        "supporting citation, and advice that overreaches what the sources support.\n"
        "Return a verdict of PASS or REVISE plus a specific list of what to change. Be concrete - "
        "'paragraph 3 asserts a 12% figure that appears in no cited source' beats 'some claims are unsupported'."
    ),
    tools=["pii_scan", "policy_lookup"],
    output_key="compliance_review",
)

WRITER = AgentSpec(
    name="writer",
    display_name="Writer",
    description="Composes the answer the user actually reads.",
    instruction=(
        "You are the Writer. Compose the final answer from the research findings, retrieved context and "
        "analysis.\n"
        "Rules: every factual claim that came from a document carries its [filename p.N] citation. Lead with "
        "the answer, then support it. Match the user's register. If the compliance review says REVISE, apply "
        "the fixes before writing. If the evidence does not support an answer, say so in the first sentence."
    ),
    tools=[],
    output_key="final_answer",
)

ORCHESTRATOR_INSTRUCTION = (
    "You are the Orchestrator of a five-agent team. You do not answer the user directly; you decide who works "
    "and in what order, then you own the quality of what comes back.\n\n"
    "Your team:\n"
    "- researcher: external and corpus-level discovery\n"
    "- retriever: hybrid search over the user's uploaded documents, returns cited passages\n"
    "- analyst: arithmetic and quantitative reasoning\n"
    "- compliance: policy, PII and unsupported-claim review\n"
    "- writer: final composition\n\n"
    "How to route:\n"
    "1. A greeting or a trivial question needs no delegation. Answer it and stop. Spinning up five agents for "
    "'hi' is a bug, not thoroughness.\n"
    "2. If the user has uploaded documents and the question touches them, retriever runs first and always.\n"
    "3. researcher and retriever can run in parallel - they do not depend on each other.\n"
    "4. analyst only runs when there are numbers to work on.\n"
    "5. compliance runs on any draft that will be shown to a user in a regulated context, and always before writer "
    "finalises.\n"
    "6. writer runs last, once.\n\n"
    "Never invent a citation. Never let a sub-agent's failure disappear silently - if retriever returns nothing, "
    "say the corpus had no match rather than answering from general knowledge as if it were sourced."
)

AGENT_SPECS: dict[str, AgentSpec] = {
    spec.name: spec for spec in (RESEARCHER, RETRIEVER, ANALYST, COMPLIANCE, WRITER)
}
DEFAULT_AGENTS: list[str] = list(AGENT_SPECS)


def specs_for(enabled: list[str] | None) -> list[AgentSpec]:
    if not enabled:
        return [AGENT_SPECS[name] for name in DEFAULT_AGENTS]
    return [AGENT_SPECS[name] for name in enabled if name in AGENT_SPECS]


def roster() -> list[dict[str, str]]:
    return [
        {
            "name": s.name,
            "display_name": s.display_name,
            "description": s.description,
            "tools": ", ".join(s.tools) or "-",
        }
        for s in AGENT_SPECS.values()
    ]
