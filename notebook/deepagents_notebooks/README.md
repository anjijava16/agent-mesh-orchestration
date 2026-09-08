# 🤖 Deep Agents Tutorial

A **beginner-friendly** guide to building AI agents with [LangChain's Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview) framework.

Deep Agents make it easy to create LLM-powered assistants that can **plan**, **use tools**, **delegate to subagents**, and **remember** things across conversations.

---

## 📁 Repository Structure

```
deepagents-tutorial/
│
├── 01_hello_world/          # Start here! Simplest possible agent
├── 02_research_agent/       # Agent that searches the web and writes reports
├── 03_memory_agent/         # Agent that remembers users across conversations
├── 04_subagents_team/       # Team of specialist agents working together
├── 05_streaming/            # Real-time token output with agent.stream()
├── 06_human_in_loop/        # Agent pauses for human approval on sensitive actions
├── 07_fastapi_server/       # Full REST API server with streaming + sessions
│
├── requirements.txt         # All Python dependencies
└── README.md                # You are here
```

---

## 🚀 Quick Start

### 1. Clone this repo

```bash
git clone https://github.com/mkassaf/deepagents-tutorial.git
cd deepagents-tutorial
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set your API keys

```bash
# Required: pick one LLM provider
export ANTHROPIC_API_KEY="your-anthropic-key"   # get at console.anthropic.com
# OR
export OPENAI_API_KEY="your-openai-key"         # get at platform.openai.com

# Required for examples 02 and 04 (web search)
export TAVILY_API_KEY="your-tavily-key"         # free tier at tavily.com
```

### 4. Run an example

```bash
# Start with the simplest one
python 01_hello_world/agent.py
```

---

## 📚 Examples Overview

| # | Example | What it teaches | Difficulty |
|---|---------|----------------|------------|
| 01 | [Hello World](./01_hello_world/) | Creating your first agent, basic tools | ⭐ Beginner |
| 02 | [Research Agent](./02_research_agent/) | Web search, planning, file system | ⭐⭐ Beginner+ |
| 03 | [Memory Agent](./03_memory_agent/) | Long-term memory across sessions | ⭐⭐⭐ Intermediate |
| 04 | [Subagents Team](./04_subagents_team/) | Multiple specialist agents, delegation | ⭐⭐⭐ Intermediate |
| 05 | [Streaming Agent](./05_streaming/) | Real-time token output, SSE streaming | ⭐⭐ Beginner+ |
| 06 | [Human-in-the-Loop](./06_human_in_loop/) | Agent pauses for human approval | ⭐⭐⭐ Intermediate |
| 07 | [FastAPI Server](./07_fastapi_server/) | REST API, multi-session, production deploy | ⭐⭐⭐ Intermediate |

---

## 🧠 How Deep Agents Work (Big Picture)

```
User asks a question
        ↓
  Deep Agent (brain)
  ├── Plans steps with write_todos
  ├── Reads/writes files to manage context
  ├── Calls your custom tools (search, APIs...)
  └── Spawns subagents for complex subtasks
        ↓
  Final answer returned to user
```

The key insight: unlike a simple chatbot, a Deep Agent **actively manages its own workflow**. It decides what to do next, tracks progress, and handles errors — just like a human assistant would.

---

## 🔑 Key Concepts

| Concept | What it is | Analogy |
|--------|-----------|---------|
| **Agent** | The main AI brain | A project manager |
| **Tool** | A Python function the agent can call | A tool in a toolbox |
| **Planner** | `write_todos` built-in tool | A to-do list |
| **File system** | read/write files for large data | A scratchpad |
| **Subagent** | A specialized mini-agent | A team member |
| **Memory** | Persistent storage across sessions | A notebook |

---

## 📦 Dependencies

- [`deepagents`](https://pypi.org/project/deepagents/) — The main framework
- [`langchain`](https://pypi.org/project/langchain/) — Core building blocks
- [`langgraph`](https://pypi.org/project/langgraph/) — Runtime for durable execution
- [`anthropic`](https://pypi.org/project/anthropic/) — Claude LLM provider
- [`tavily-python`](https://pypi.org/project/tavily-python/) — Web search API

---

## 📖 Further Reading

- [Deep Agents Official Docs](https://docs.langchain.com/oss/python/deepagents/overview)
- [LangChain Docs](https://docs.langchain.com/oss/python/langchain/overview)
- [LangGraph Docs](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangSmith (for debugging)](https://smith.langchain.com/)

---

## 🤝 Contributing

Found a bug or want to add an example? Open an issue or PR!

---

*Built with ❤️ using [LangChain Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview)*
