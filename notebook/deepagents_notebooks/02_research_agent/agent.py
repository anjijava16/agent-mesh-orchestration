# ============================================================
# Example 02: Research Agent — Web Search + Planning + Reports
# ============================================================
#
# This agent demonstrates Deep Agents' most powerful features:
#
#   1. PLANNING     — The agent breaks complex tasks into steps (write_todos)
#   2. WEB SEARCH   — Searches the internet using Tavily
#   3. FILE SYSTEM  — Saves large search results to files to avoid
#                     overflowing the LLM's context window
#   4. REPORT       — Synthesizes findings into a polished markdown report
#
# Prerequisites:
#   pip install deepagents tavily-python
#   export ANTHROPIC_API_KEY="your-key"
#   export TAVILY_API_KEY="your-key"  ← free at https://tavily.com
#
# Run this file:
#   python 02_research_agent/agent.py
# ============================================================

import os
from typing import Literal
from deepagents import create_deep_agent

# ── TOOL: Internet Search ─────────────────────────────────────
#
# We define a search tool that wraps the Tavily API.
# Tavily is a search engine built specifically for AI agents —
# it returns clean, structured results that are easy for LLMs to process.
#
# The agent will call this function whenever it needs to look something up.

def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
) -> dict:
    """
    Search the internet for information on any topic.

    Use this tool whenever you need current information about something.
    You can search for general information, recent news, or financial data.

    Args:
        query: The search query string (e.g. "climate change 2024 solutions")
        max_results: How many results to return (default 5, max 10)
        topic: Type of search — "general" for facts, "news" for recent events,
               "finance" for stock/market data
        include_raw_content: If True, includes full page content in results
                             (useful for in-depth research, uses more tokens)

    Returns:
        A dict with search results including titles, URLs, and snippets.
    """
    # Import here so the file still loads if Tavily isn't installed
    try:
        from tavily import TavilyClient
    except ImportError:
        return {"error": "tavily-python not installed. Run: pip install tavily-python"}

    # Get the API key from environment variable
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return {"error": "TAVILY_API_KEY environment variable not set"}

    client = TavilyClient(api_key=api_key)

    # Perform the search and return results
    results = client.search(
        query=query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )
    return results


# ── TOOL: Save Report ─────────────────────────────────────────
#
# This tool lets the agent save its final report to a local file.
# The agent will call this automatically when it finishes research.

def save_report(filename: str, content: str) -> str:
    """
    Save a research report to a local markdown file.

    Use this tool when you have finished your research and want to
    save the final report so the user can access it later.

    Args:
        filename: The filename to save to (e.g. "climate_report.md")
        content: The full markdown content of the report

    Returns:
        A confirmation message with the file path.
    """
    # Ensure the reports directory exists
    os.makedirs("reports", exist_ok=True)

    # Clean the filename (remove any path traversal attempts)
    safe_filename = os.path.basename(filename)
    if not safe_filename.endswith(".md"):
        safe_filename += ".md"

    filepath = os.path.join("reports", safe_filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return f"✅ Report saved to: {filepath}"


# ── SYSTEM PROMPT ─────────────────────────────────────────────
#
# The system prompt acts as the agent's "job description".
# For a research agent, we want it to:
#   - Plan before diving in
#   - Search multiple times for thorough coverage
#   - Write a well-structured report

RESEARCH_SYSTEM_PROMPT = """You are an expert research analyst. Your mission is to conduct 
thorough, accurate research on any topic and produce a polished, well-structured report.

## Your Research Process

Always follow these steps in order:

1. **Plan first** — Use write_todos to break the research into clear steps before starting
2. **Search broadly** — Run at least 3-5 searches to cover the topic from multiple angles
3. **Go deep** — For key sources, use include_raw_content=True to get full details
4. **Verify facts** — Cross-reference important claims across multiple sources
5. **Write the report** — Synthesize findings into a clear, well-structured markdown report
6. **Save it** — Use save_report to save the final report to a file

## Report Structure

Your final report should always include:
- **Executive Summary** — 2-3 sentence overview
- **Background** — Context and history
- **Key Findings** — Main discoveries from your research (use bullet points)
- **Analysis** — Your interpretation and insights
- **Sources** — List all URLs you used

## Important Notes

- Always cite your sources with URLs
- Be objective and balanced
- Use clear, accessible language
- If information is conflicting across sources, note the discrepancy
- Prioritize recent sources (last 12 months) for fast-moving topics
"""

# ── CREATE THE AGENT ──────────────────────────────────────────
#
# Note: We pass both tools — internet_search for gathering data
# and save_report for persisting the final output.
# The agent also gets built-in tools automatically:
#   - write_todos (planning)
#   - write_file / read_file (context management)

agent = create_deep_agent(
    tools=[internet_search, save_report],
    system_prompt=RESEARCH_SYSTEM_PROMPT,
)


# ── HELPER: Run a research task ───────────────────────────────

def research(topic: str) -> str:
    """
    Ask the research agent to investigate a topic and return its report.

    Args:
        topic: The research topic or question (be specific for better results)

    Returns:
        The agent's final research report as a string.
    """
    print(f"\n🔍 Starting research on: '{topic}'")
    print("   (The agent will plan, search, and write a report...)\n")

    result = agent.invoke({
        "messages": [
            {
                "role": "user",
                # We ask for a specific output format in the user message too
                # to reinforce the system prompt instructions
                "content": (
                    f"Please research the following topic thoroughly and write "
                    f"a detailed report:\n\n{topic}\n\n"
                    f"Remember to: plan first, search multiple times, "
                    f"and save the final report to a file."
                )
            }
        ]
    })

    # The final message contains the agent's summary response
    return result["messages"][-1].content


# ── DEMO ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🔬 Research Agent Demo")
    print("=" * 60)

    # ── Demo 1: General research topic
    print("\n--- RESEARCH TASK 1: Technology Topic ---")
    answer1 = research(
        "What are the most promising AI agent frameworks in 2024-2025? "
        "Compare LangChain, LangGraph, AutoGen, and CrewAI."
    )
    print("\n📄 Agent Summary:")
    print(answer1)

    # ── Demo 2: News research (recent events)
    print("\n\n--- RESEARCH TASK 2: Recent News ---")
    answer2 = research(
        "What are the latest developments in quantum computing? "
        "Focus on breakthroughs from the last 6 months."
    )
    print("\n📄 Agent Summary:")
    print(answer2)

    print("\n" + "=" * 60)
    print("✅ Reports saved to ./reports/ folder")
    print("=" * 60)
