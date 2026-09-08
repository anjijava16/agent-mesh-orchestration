# 03 — Memory Agent: Remembering Users Across Conversations

> **Difficulty:** ⭐⭐⭐ Intermediate

By default, every call to `agent.invoke()` starts fresh — the agent forgets everything. This example teaches you how to build agents that **remember users** across multiple sessions, storing preferences and facts for future conversations.

---

## 🎯 What You'll Learn

- Why agents forget things by default and how memory works
- How to use **thread IDs** to manage conversation sessions
- How to build **memory tools** (remember, recall, forget)
- How to write a system prompt that instructs the agent to use memory naturally
- The difference between **short-term memory** (within a session) and **long-term memory** (across sessions)

---

## 📂 Files

```
03_memory_agent/
├── agent.py           # Memory agent with 3 memory tools
├── memory_user001.json  # Saved memories (auto-created when you run)
└── README.md          # This file
```

---

## 🧠 Memory: The Big Concept

### Without memory (default behavior)

```
Session 1: "My name is Marco"  →  Agent: "Nice to meet you, Marco!"
Session 2: "Hi again!"         →  Agent: "Hello! What's your name?"  ← Forgot!
```

### With long-term memory

```
Session 1: "My name is Marco"  →  Agent saves: {name: "Marco"}
                                   Agent: "Nice to meet you, Marco!"

Session 2: "Hi again!"         →  Agent recalls: {name: "Marco"}
                                   Agent: "Welcome back, Marco!" ← Remembered!
```

---

## 🔧 The 3 Memory Tools

| Tool | What it does |
|------|-------------|
| `remember_user_info(key, value)` | Saves a fact about the user |
| `recall_user_info(key)` | Retrieves saved facts |
| `forget_user_info(key)` | Deletes a saved fact |

### Example tool calls the agent makes automatically

```python
# When user says "My name is Marco"
remember_user_info(key="name", value="Marco")

# When user says "What do you know about me?"
recall_user_info()  # Returns all saved info

# When user says "I moved to Milan"
forget_user_info(key="city")
remember_user_info(key="city", value="Milan")
```

---

## 🔑 Key Concept: Thread IDs

LangGraph uses **thread IDs** to separate conversations:

```python
# Same thread_id = same session context (agent remembers the conversation)
chat("My name is Marco", thread_id="session_001")
chat("What's my name?",  thread_id="session_001")  # → "Marco"

# Different thread_id = new session (but long-term memory still works)
chat("Hi!",              thread_id="session_002")   # → "Hi Marco!" (from memory)
```

Think of `thread_id` like a WhatsApp chat thread — switching to a new one starts a fresh conversation, but the agent's long-term memory persists across all threads.

---

## 💾 How Memory is Stored

In this demo, memories are saved to a local JSON file (`memory_user001.json`). After running the example it will look like:

```json
{
  "name": "Marco",
  "city": "Milan",
  "job": "software engineer",
  "hobby": "cooking Italian food",
  "temperature_preference": "Celsius"
}
```

In production you'd replace the JSON file with:
- **LangGraph Memory Store** (built-in, backed by any database)
- **Redis** for fast distributed storage
- **PostgreSQL** for structured data with querying

---

## 📋 The System Prompt Pattern

The key to making memory work naturally is a clear system prompt:

```python
MEMORY_SYSTEM_PROMPT = """
At the START of every conversation:
- Always call recall_user_info() to load what you know
- Greet the user by name if you know it

During the conversation:
- When the user tells you something personal, IMMEDIATELY call remember_user_info()
- When the user says "remember that...", always save it
- When the user says "forget that...", use forget_user_info()
"""
```

This turns memory into an automatic behavior rather than something you have to trigger manually.

---

## ▶️ How to Run

```bash
# From the repo root:
python 03_memory_agent/agent.py
```

### Expected Output

```
============================================================
🧠 Memory Agent Demo
============================================================

📅 SESSION 1 — First time talking to the agent
----------------------------------------
User: Hi! My name is Marco. I live in Rome...
Agent: Nice to meet you, Marco! I've noted that you're based in Rome
       and work as a software engineer. Italian cooking is a wonderful hobby!

📅 SESSION 2 — New session (different thread_id)
----------------------------------------
User: Hello again!
Agent: Welcome back, Marco! Great to hear from you again.
       How have things been in Rome?

User: What's a good recipe I could cook this weekend?
Agent: Since I know you love Italian cooking and you're vegetarian,
       here's a fantastic Cacio e Pepe recipe that would be perfect...
```

---

## 💡 Tips for Production Memory Agents

1. **Extract memories automatically** — Use LangGraph's built-in memory extraction to save key facts without needing explicit tool calls
2. **Namespace memories by user** — Use user IDs to keep memories separate (`user_001`, `user_002`)
3. **Set memory expiry** — Some facts (like preferences) last forever; others (like "I'm in Paris this week") should expire
4. **Let users see their data** — Always provide a way for users to view and delete their stored memories (GDPR compliance)

---

## ➡️ Next Steps

Move on to **[04 — Subagents Team](../04_subagents_team/)** to learn how to build a team of specialized agents that work together.
