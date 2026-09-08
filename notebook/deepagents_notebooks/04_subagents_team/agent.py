# ============================================================
# Example 04: Subagents Team — Multiple Specialist Agents
# ============================================================
#
# Sometimes one agent isn't enough. Complex tasks benefit from
# a TEAM of specialized agents, each an expert in one area.
#
# This example builds a Content Creation Pipeline with 4 agents:
#
#   ORCHESTRATOR  — The manager. Receives the user's request,
#                   delegates work to specialists, combines results.
#
#   RESEARCHER    — Specialist 1. Searches the web, gathers facts,
#                   and writes a structured research brief.
#
#   WRITER        — Specialist 2. Takes the research brief and writes
#                   a high-quality blog post draft.
#
#   EDITOR        — Specialist 3. Reviews the draft, improves clarity,
#                   fixes grammar, and produces the final polished article.
#
# Why use subagents instead of one big agent?
#   ✅ Each agent has a focused context — no information overload
#   ✅ Each can use different tools suited to its job
#   ✅ Agents can work in parallel (advanced use case)
#   ✅ Easier to debug — you can see each agent's output separately
#   ✅ Each agent's system prompt is tuned for its specialty
#
# Run this file:
#   python 04_subagents_team/agent.py
# ============================================================

import os
from typing import Literal
from deepagents import create_deep_agent


# ════════════════════════════════════════════════════════════
# SPECIALIST AGENT 1: The Researcher
# ════════════════════════════════════════════════════════════

def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
) -> dict:
    """
    Search the internet for information on a given topic.

    Args:
        query: Search query string
        max_results: Number of results to return (default 5)
        topic: Type of search — general, news, or finance

    Returns:
        Search results with titles, URLs, and snippets.
    """
    try:
        from tavily import TavilyClient
    except ImportError:
        # Graceful fallback if Tavily isn't installed
        return {
            "results": [
                {
                    "title": "Mock Result (install tavily-python for real search)",
                    "content": f"This is a mock result for query: '{query}'. "
                               "In production, this would be real web content.",
                    "url": "https://example.com",
                }
            ]
        }

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return {"error": "TAVILY_API_KEY not set. Set it to enable web search."}

    client = TavilyClient(api_key=api_key)
    return client.search(query=query, max_results=max_results, topic=topic)


# The researcher agent: focused entirely on gathering and organizing information
researcher_agent = create_deep_agent(
    tools=[internet_search],
    system_prompt="""You are a specialist research agent. Your ONLY job is to 
research topics thoroughly and produce a structured research brief.

## Your Output Format

Always produce a research brief with these exact sections:

### TOPIC
(State the topic clearly)

### KEY FACTS
- (Bullet point 1)
- (Bullet point 2)
- (At least 5-8 key facts from your research)

### STATISTICS & DATA
- (Any relevant numbers, percentages, dates)

### EXPERT OPINIONS
- (Quotes or paraphrased views from experts/sources)

### SOURCES
- [Title](URL)
- (List every source you used)

## Instructions
- Run at least 4-5 different searches to cover the topic broadly
- Focus on facts, not opinions
- Include recent information (prefer sources from last 12 months)
- Be thorough — the writer depends on your brief to create quality content
""",
)


# ════════════════════════════════════════════════════════════
# SPECIALIST AGENT 2: The Writer
# ════════════════════════════════════════════════════════════

# The writer agent: takes research briefs and writes engaging blog posts
writer_agent = create_deep_agent(
    tools=[],  # The writer doesn't need any external tools
    system_prompt="""You are a specialist content writer agent. Your ONLY job is to 
take a research brief and turn it into an engaging, well-written blog post.

## Your Writing Style
- Conversational yet informative tone
- Use the inverted pyramid: start with the most important info
- Short paragraphs (2-4 sentences max)
- Use headers (##) to organize sections
- Use bullet points sparingly — prefer flowing prose
- Start with a hook that grabs attention
- End with a clear takeaway or call to action

## Blog Post Structure
1. **Headline** — Compelling, specific, uses power words
2. **Introduction** (2-3 paragraphs) — Hook + why this matters
3. **Main Body** (4-6 sections with ## headers)
4. **Conclusion** — Key takeaway and call to action

## Instructions
- Base your writing ONLY on the research brief provided
- Do not invent facts or statistics
- Aim for 600-900 words
- Make it engaging for a general audience
- Do not include sources in the body — save them for the end
""",
)


# ════════════════════════════════════════════════════════════
# SPECIALIST AGENT 3: The Editor
# ════════════════════════════════════════════════════════════

# The editor agent: polishes drafts and makes them publication-ready
editor_agent = create_deep_agent(
    tools=[],  # The editor works only with text — no tools needed
    system_prompt="""You are a specialist editor agent. Your ONLY job is to review 
a blog post draft and produce a polished, publication-ready final version.

## What You Check For

**Clarity**
- Is every sentence easy to understand?
- Are any sentences too long or complex? Break them up.
- Is jargon explained or replaced with plain language?

**Flow**
- Do paragraphs connect logically?
- Are transitions smooth between sections?
- Does the article build momentum from intro to conclusion?

**Grammar & Style**
- Fix all grammar and spelling errors
- Ensure consistent tense (past/present)
- Remove redundant words and phrases
- Check that headers are in sentence case

**Engagement**
- Is the opening hook compelling?
- Does the conclusion leave the reader satisfied?
- Are there any weak or vague sentences to strengthen?

## Output Format

First, provide a brief EDITOR'S NOTE (3-5 bullet points) summarizing what you changed.
Then provide the FINAL ARTICLE in full.

Format:
---
**EDITOR'S NOTE**
- (Change 1)
- (Change 2)

---
**FINAL ARTICLE**

(Full polished article here)
""",
)


# ════════════════════════════════════════════════════════════
# THE ORCHESTRATOR: Pipeline Manager
# ════════════════════════════════════════════════════════════
#
# The orchestrator is NOT an agent itself — it's a Python function
# that coordinates the three specialist agents.
#
# This is one pattern for multi-agent systems: a simple Python
# function that chains agent calls. Another pattern (more advanced)
# is to make the orchestrator itself an agent that uses the other
# agents as tools via the built-in `task` tool.

def content_pipeline(topic: str, verbose: bool = True) -> dict:
    """
    Run the full content creation pipeline for a given topic.

    This orchestrates three specialist agents in sequence:
    1. Researcher → gathers facts and data
    2. Writer     → turns research into a blog post draft
    3. Editor     → polishes the draft into a final article

    Args:
        topic: The topic to write about (be specific for best results)
        verbose: If True, prints progress updates

    Returns:
        A dict with the research_brief, draft, and final_article.
    """

    # ── STAGE 1: Research ────────────────────────────────────
    if verbose:
        print(f"\n🔍 Stage 1/3: Researcher is gathering information on '{topic}'...")

    # Invoke the researcher agent with the topic
    research_result = researcher_agent.invoke({
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Please research this topic thoroughly and produce "
                    f"a structured research brief:\n\n{topic}"
                )
            }
        ]
    })

    # Extract the research brief from the last message
    research_brief = research_result["messages"][-1].content

    if verbose:
        print("   ✅ Research complete!")
        print(f"   📋 Brief length: {len(research_brief.split())} words")

    # ── STAGE 2: Writing ─────────────────────────────────────
    if verbose:
        print("\n✍️  Stage 2/3: Writer is drafting the blog post...")

    # Pass the research brief to the writer agent
    # Note: we include the full research brief in the message
    write_result = writer_agent.invoke({
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Please write an engaging blog post based on this research brief.\n\n"
                    f"TOPIC: {topic}\n\n"
                    f"RESEARCH BRIEF:\n{research_brief}"
                )
            }
        ]
    })

    draft = write_result["messages"][-1].content

    if verbose:
        print("   ✅ Draft complete!")
        print(f"   📝 Draft length: {len(draft.split())} words")

    # ── STAGE 3: Editing ──────────────────────────────────────
    if verbose:
        print("\n✏️  Stage 3/3: Editor is polishing the draft...")

    # Pass the draft to the editor agent
    edit_result = editor_agent.invoke({
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Please review and polish this blog post draft:\n\n{draft}"
                )
            }
        ]
    })

    final_article = edit_result["messages"][-1].content

    if verbose:
        print("   ✅ Editing complete!")
        print(f"   📄 Final article length: {len(final_article.split())} words")

    return {
        "topic": topic,
        "research_brief": research_brief,
        "draft": draft,
        "final_article": final_article,
    }


# ── HELPER: Save output to files ─────────────────────────────

def save_pipeline_output(result: dict) -> None:
    """Save all pipeline stages to files for easy review."""
    os.makedirs("output", exist_ok=True)

    # Create a safe filename from the topic
    safe_topic = "".join(c if c.isalnum() else "_" for c in result["topic"])[:40]

    # Save research brief
    with open(f"output/{safe_topic}_research.md", "w") as f:
        f.write(f"# Research Brief: {result['topic']}\n\n")
        f.write(result["research_brief"])

    # Save draft
    with open(f"output/{safe_topic}_draft.md", "w") as f:
        f.write(f"# Draft: {result['topic']}\n\n")
        f.write(result["draft"])

    # Save final article
    with open(f"output/{safe_topic}_final.md", "w") as f:
        f.write(result["final_article"])

    print(f"\n💾 Files saved to ./output/")
    print(f"   • {safe_topic}_research.md  ← Research brief")
    print(f"   • {safe_topic}_draft.md     ← Writer's first draft")
    print(f"   • {safe_topic}_final.md     ← Polished final article")


# ── DEMO ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🏭 Content Creation Pipeline (3-Agent Team)")
    print("=" * 60)
    print("Agents: Researcher → Writer → Editor")

    # Run the full pipeline on a topic
    topic = (
        "The rise of AI agents in 2025: "
        "how autonomous AI assistants are changing the way we work"
    )

    print(f"\n📌 Topic: {topic}")

    # Run the pipeline (verbose=True shows progress at each stage)
    result = content_pipeline(topic, verbose=True)

    # Save all stages to files
    save_pipeline_output(result)

    # Print a snippet of the final article
    print("\n" + "=" * 60)
    print("📰 Final Article (Preview):")
    print("=" * 60)
    # Show just the first 500 characters as a preview
    preview = result["final_article"][:500]
    print(preview + "...")
    print("\n(Full article saved to ./output/)")
    print("=" * 60)
