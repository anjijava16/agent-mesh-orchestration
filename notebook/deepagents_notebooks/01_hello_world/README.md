# 01 — Hello World: Your First Deep Agent

> **Difficulty:** ⭐ Beginner — Start here!

This is the simplest possible Deep Agent. It demonstrates the three fundamental building blocks you need to understand before anything else.

---

## 🎯 What You'll Learn

- What a **tool** is and how to write one
- How to create an agent with `create_deep_agent()`
- How to send a message to the agent and get a response
- How agents can call **multiple tools** in a single response

---

## 📂 Files

```
01_hello_world/
├── agent.py      # The full agent with 3 tools and demo questions
└── README.md     # This file
```

---

## 🧠 Key Concepts Explained

### What is a Tool?

A tool is just a **regular Python function** that the agent can call. You don't call it yourself — the agent decides when to use it based on the user's question.

```python
def get_weather(city: str) -> str:
    """Get the current weather for a given city."""  # Agent reads this!
    return f"It's sunny in {city}!"
```

Three things matter for a tool:
1. **The function name** — tells the agent what it does (`get_weather`)
2. **The docstring** — the agent reads this to understand when to use it
3. **The type hints** — tells the agent what arguments to pass (`city: str`)

### What is create_deep_agent()?

```python
agent = create_deep_agent(
    tools=[get_weather, get_time, convert_currency],
    system_prompt="You are a travel assistant..."
)
```

This creates an agent that:
- Uses Claude (or OpenAI) as its brain
- Has access to the 3 tools you passed in
- Follows the personality defined in `system_prompt`
- Automatically gets planning + file system capabilities built in

### How do you run the agent?

```python
result = agent.invoke({
    "messages": [{"role": "user", "content": "What's the weather in Rome?"}]
})

# The final answer is always the last message
answer = result["messages"][-1].content
```

---

## 🔧 The 3 Tools in This Example

| Tool | What it does |
|------|-------------|
| `get_weather(city)` | Returns current weather for a city |
| `get_time(city)` | Returns local time for a city |
| `convert_currency(amount, from, to)` | Converts between currencies |

> **Note:** In this demo the tools return hardcoded data. In a real application you'd connect them to real APIs (OpenWeatherMap, exchange rate APIs, etc.).

---

## ▶️ How to Run

```bash
# From the repo root:
python 01_hello_world/agent.py
```

### Expected Output

```
============================================================
🤖 Hello World Deep Agent
============================================================

📍 Question 1: Weather
----------------------------------------
The weather in Rome today is sunny and 24°C — a perfect day to go outside!

📍 Question 2: Time
----------------------------------------
The current local time in Tokyo is 14:35 (2:35 PM).

📍 Question 3: Multi-tool (weather + time + currency)
----------------------------------------
Here's everything for your Paris trip:
- 🌤️ Weather: Sunny and 24°C
- 🕐 Local time: 14:35 (2:35 PM)
- 💶 Currency: 200 USD = 184.00 EUR
```

---

## 💡 What Happens Behind the Scenes?

When you ask "What's the weather in Rome?", the agent:

1. Reads your message
2. Decides it needs to call `get_weather("Rome")`
3. Calls the function and gets the result
4. Formats a friendly answer and returns it

When you ask a multi-part question, the agent:

1. Reads your message
2. Plans: "I need to call `get_weather`, `get_time`, AND `convert_currency`"
3. Calls all three tools
4. Combines all results into one coherent response

---

## ➡️ Next Steps

Once you're comfortable with this example, move on to:

**[02 — Research Agent](../02_research_agent/)** — an agent that searches the web, plans multi-step research tasks, and writes full reports.
