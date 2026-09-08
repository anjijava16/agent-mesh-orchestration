# 04 — Subagents Team: Multiple Specialist Agents

> **Difficulty:** ⭐⭐⭐ Intermediate

Instead of one agent trying to do everything, this example builds a **team of three specialist agents** that work together like a professional content team: a Researcher, a Writer, and an Editor.

---

## 🎯 What You'll Learn

- Why and when to use **multiple agents** instead of one
- How to build **specialist agents** with focused system prompts
- How to **chain agents** so the output of one becomes the input of the next
- How to **orchestrate** a multi-agent pipeline
- The difference between an **orchestrator pattern** and a **subagent-as-tool pattern**

---

## 📂 Files

```
04_subagents_team/
├── agent.py        # 3 specialist agents + pipeline orchestrator
├── output/         # Final articles saved here (auto-created)
└── README.md       # This file
```

---

## 🏭 The Content Creation Pipeline

```
User: "Write an article about AI agents in 2025"
              │
              ▼
    ┌─────────────────┐
    │   ORCHESTRATOR  │  (Python function — coordinates the pipeline)
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │   RESEARCHER    │  Searches the web → produces research brief
    │  (Agent #1)     │  Tools: internet_search
    └────────┬────────┘
             │ research brief
    ┌────────▼────────┐
    │    WRITER       │  Takes brief → writes blog post draft
    │  (Agent #2)     │  Tools: none (pure writing)
    └────────┬────────┘
             │ draft
    ┌────────▼────────┐
    │    EDITOR       │  Reviews draft → polished final article
    │  (Agent #3)     │  Tools: none (pure editing)
    └────────┬────────┘
             │
             ▼
    Final article saved to ./output/
```

---

## 🧠 Why Use Multiple Agents?

| Problem | Single Agent | Multi-Agent Team |
|---------|-------------|-----------------|
| Context overload | Agent tries to do research + writing + editing simultaneously, confuses them | Each agent only sees what it needs |
| Quality | System prompt must balance many goals | Each agent has a laser-focused system prompt |
| Debugging | Hard to tell which step failed | Easy to inspect each stage's output separately |
| Specialization | Generic performance at everything | Expert-level at each stage |

---

## 🤖 The Three Specialist Agents

### Agent 1: The Researcher
- **Tools:** `internet_search`
- **Job:** Run 4-5 searches, gather facts, produce a structured research brief
- **Output format:** Structured markdown with Key Facts, Statistics, Sources

### Agent 2: The Writer
- **Tools:** None (pure text generation)
- **Job:** Transform the research brief into an engaging blog post
- **Output format:** Full blog post with hook, headers, flowing prose

### Agent 3: The Editor
- **Tools:** None (pure text review)
- **Job:** Fix grammar, improve clarity, strengthen engagement
- **Output format:** Editor's notes + polished final article

---

## 🔑 Key Code Patterns

### Focused system prompts

Each agent has a system prompt that starts with exactly what its job is:

```python
researcher_system = """You are a specialist research agent.
Your ONLY job is to research topics and produce a structured brief..."""

writer_system = """You are a specialist content writer agent.
Your ONLY job is to take a research brief and write a blog post..."""
```

The words "Your ONLY job" keep the agent from scope-creeping into other roles.

### Passing output between agents

```python
# Stage 1: Research
research_result = researcher_agent.invoke({
    "messages": [{"role": "user", "content": f"Research: {topic}"}]
})
research_brief = research_result["messages"][-1].content  # Extract output

# Stage 2: Writing — pass research brief as context
write_result = writer_agent.invoke({
    "messages": [{
        "role": "user",
        "content": f"Write a blog post based on this brief:\n\n{research_brief}"
    }]
})
```

The output of one agent becomes part of the input message to the next.

---

## ▶️ How to Run

```bash
# Optional: set Tavily key for real web search
export TAVILY_API_KEY="your-tavily-key"

# From the repo root:
python 04_subagents_team/agent.py
```

### Expected Output

```
============================================================
🏭 Content Creation Pipeline (3-Agent Team)
============================================================
Agents: Researcher → Writer → Editor

📌 Topic: The rise of AI agents in 2025...

🔍 Stage 1/3: Researcher is gathering information...
   ✅ Research complete!
   📋 Brief length: 420 words

✍️  Stage 2/3: Writer is drafting the blog post...
   ✅ Draft complete!
   📝 Draft length: 750 words

✏️  Stage 3/3: Editor is polishing the draft...
   ✅ Editing complete!
   📄 Final article length: 720 words

💾 Files saved to ./output/
   • The_rise_of_AI_agents_research.md
   • The_rise_of_AI_agents_draft.md
   • The_rise_of_AI_agents_final.md

============================================================
📰 Final Article (Preview):
============================================================
# The Rise of AI Agents in 2025: How Autonomous Assistants Are Changing Work

The way we work is changing faster than most people realize...
```

---

## 💡 Two Patterns for Multi-Agent Systems

This example uses the **Pipeline Pattern** (simplest):

```
Agent A → Agent B → Agent C
```

Deep Agents also supports the **Orchestrator-as-Agent Pattern** (more flexible):

```python
# Make each specialist agent a callable tool
def run_researcher(task: str) -> str:
    """Research a topic and return a structured brief."""
    result = researcher_agent.invoke({"messages": [{"role": "user", "content": task}]})
    return result["messages"][-1].content

# Give those tools to a manager agent
orchestrator = create_deep_agent(
    tools=[run_researcher, run_writer, run_editor],
    system_prompt="You are a content manager. Delegate to your specialists..."
)
```

The orchestrator agent then decides dynamically which specialists to call and in what order — useful for non-linear workflows.

---

## ➡️ What's Next?

You've completed all four examples! Here's where to go from here:

- **[LangGraph Docs](https://docs.langchain.com/oss/python/langgraph)** — for production-grade multi-agent systems
- **[LangSmith](https://smith.langchain.com/)** — to trace and debug your agents visually
- **[Deep Agents Backends](https://docs.langchain.com/oss/python/deepagents/backends)** — for production file storage
- **[Human-in-the-Loop](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)** — add human approval steps to your pipeline
