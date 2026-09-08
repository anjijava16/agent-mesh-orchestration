# 02 — Research Agent: Web Search + Planning + Reports

> **Difficulty:** ⭐⭐ Beginner+

This agent searches the web, plans multi-step research tasks, and produces polished markdown reports. It showcases the features that make Deep Agents genuinely powerful.

---

## 🎯 What You'll Learn

- How agents **plan** complex tasks using the built-in `write_todos` tool
- How to give an agent a **web search tool** using Tavily
- How agents use **file system tools** to handle large amounts of data
- How to write a detailed **system prompt** that shapes agent behavior
- How to have the agent **save results** to a file

---

## 📂 Files

```
02_research_agent/
├── agent.py      # Research agent with web search + report saving
├── reports/      # Reports are saved here (created automatically)
└── README.md     # This file
```

---

## 🧠 How It Works

When you give the agent a research topic, here's what happens step by step:

```
User: "Research AI agent frameworks in 2025"
          │
          ▼
1. PLAN   Agent calls write_todos:
          ☐ Search for main AI frameworks
          ☐ Search for LangChain specifics
          ☐ Search for AutoGen and CrewAI
          ☐ Compare features
          ☐ Write report
          ☐ Save report
          │
          ▼
2. SEARCH Agent calls internet_search("AI agent frameworks 2025")
          Agent calls internet_search("LangChain vs AutoGen comparison")
          Agent calls internet_search("CrewAI features 2025")
          → Large results written to agent's virtual file system
          │
          ▼
3. WRITE  Agent reads its saved files + synthesizes a report
          │
          ▼
4. SAVE   Agent calls save_report("ai_frameworks.md", content)
          → File saved to ./reports/ai_frameworks.md
          │
          ▼
5. RETURN Agent returns a summary to the user
```

### Why does it use the file system?

Search results can be thousands of words long. If the agent tried to keep all of them in memory at once, it would overflow the LLM's context window. Instead, Deep Agents automatically write large results to a virtual file system and read them back as needed — like a human researcher taking notes.

---

## 🔧 Tools in This Example

| Tool | What it does |
|------|-------------|
| `internet_search(query, ...)` | Searches the web using Tavily API |
| `save_report(filename, content)` | Saves the final report to a `.md` file |
| `write_todos` *(built-in)* | Plans the research steps |
| `write_file` *(built-in)* | Saves large search results temporarily |
| `read_file` *(built-in)* | Reads back saved results when needed |

---

## ⚙️ Setup

### Get a Tavily API Key (free)

1. Go to [tavily.com](https://tavily.com)
2. Sign up for a free account
3. Copy your API key from the dashboard

### Set Environment Variables

```bash
export ANTHROPIC_API_KEY="your-anthropic-key"
export TAVILY_API_KEY="your-tavily-key"
```

### Install Dependencies

```bash
pip install deepagents tavily-python
```

---

## ▶️ How to Run

```bash
# From the repo root:
python 02_research_agent/agent.py
```

### Expected Output

```
============================================================
🔬 Research Agent Demo
============================================================

--- RESEARCH TASK 1: Technology Topic ---

🔍 Starting research on: 'What are the most promising AI agent frameworks...'
   (The agent will plan, search, and write a report...)

📄 Agent Summary:
I've completed my research on AI agent frameworks. Here's a brief summary:

**LangChain** remains the most popular framework with the largest ecosystem...
**LangGraph** excels at complex stateful workflows...
**AutoGen** from Microsoft specializes in multi-agent conversations...
**CrewAI** offers the simplest API for team-based agents...

The full report has been saved to: reports/ai_frameworks.md

============================================================
✅ Reports saved to ./reports/ folder
============================================================
```

---

## 💡 Key Code Patterns

### Multi-step system prompt

```python
RESEARCH_SYSTEM_PROMPT = """You are an expert research analyst...

## Your Research Process
1. Plan first — Use write_todos to break the research into steps
2. Search broadly — Run at least 3-5 searches
3. Go deep — Use include_raw_content=True for key sources
...
"""
```

A detailed system prompt with numbered steps dramatically improves agent behavior. The agent treats these instructions as its operating procedure.

### Typed tool arguments

```python
def internet_search(
    query: str,
    topic: Literal["general", "news", "finance"] = "general",
) -> dict:
```

Using `Literal` types restricts what values the agent can pass — it can only choose from the three options you defined. This prevents mistakes and improves reliability.

---

## ➡️ Next Steps

Move on to **[03 — Memory Agent](../03_memory_agent/)** to learn how agents can remember information across multiple conversations.
