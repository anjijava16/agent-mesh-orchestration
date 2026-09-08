# 05 — Streaming Agent: Real-Time Token Output

> **Difficulty:** ⭐⭐ Beginner+

By default `agent.invoke()` makes you wait for the **entire** response before showing anything. Streaming fixes this — tokens appear on screen as the model generates them, just like ChatGPT's typing effect.

---

## 🎯 What You'll Learn

- The difference between `invoke()` and `stream()`
- How to use `agent.stream()` with `stream_mode="messages"`
- How to detect and display **tool calls** during streaming
- How to use `astream_events()` for full event-level visibility
- When to use streaming vs invoke in production

---

## 📂 Files

```
05_streaming/
├── agent.py      # Streaming agent with 3 demos
└── README.md     # This file
```

---

## ⚡ invoke() vs stream() — The Key Difference

```
invoke()                         stream()
────────────────────             ────────────────────────────────
                                 H
                                 He
                                 Her
[waiting...]                     Here
[waiting...]                     Here i
[waiting...]                     Here is
[waiting...]          vs         Here is y
[waiting...]                     Here is yo
[waiting...]                     Here is you
[waiting...]                     Here is your
"Here is your answer!"           Here is your answer!
      ↑                                ↑
  All at once                   Token by token
  (bad UX for long responses)   (great UX always)
```

### When to use each

| Situation | Use |
|-----------|-----|
| Short responses (< 2 seconds) | Either is fine |
| Long responses | `stream()` — users see progress |
| Chat interfaces / web UI | `stream()` — always |
| Batch processing / scripts | `invoke()` — simpler |
| Need the full result before acting on it | `invoke()` |
| Piping output to a user | `stream()` |

---

## 🔧 The Code Pattern

### Basic streaming

```python
for chunk, metadata in agent.stream(
    input={"messages": [{"role": "user", "content": question}]},
    stream_mode="messages",  # ← gives token-by-token output
):
    if hasattr(chunk, "content") and chunk.content:
        print(chunk.content, end="", flush=True)  # ← print immediately, no newline

print()  # newline at the end
```

Three things make this work:
1. `agent.stream()` instead of `agent.invoke()`
2. `stream_mode="messages"` for token-level chunks
3. `end=""` and `flush=True` — print immediately without buffering

### Detecting tool calls during streaming

```python
for chunk, metadata in agent.stream(..., stream_mode="messages"):
    if hasattr(chunk, "content") and chunk.content:
        print(chunk.content, end="", flush=True)

    elif hasattr(chunk, "tool_calls") and chunk.tool_calls:
        for call in chunk.tool_calls:
            print(f"\n[🔧 Using tool: {call['name']}]")
```

### Full event streaming (for debugging)

```python
for event in agent.astream_events(input={...}, version="v2"):
    if event["event"] == "on_chat_model_stream":
        print(event["data"]["chunk"].content, end="", flush=True)

    elif event["event"] == "on_tool_start":
        print(f"\n[Tool: {event['name']}]")

    elif event["event"] == "on_tool_end":
        print(f"[Result: {event['data']['output']}]")
```

---

## 🌐 Streaming in a Web App

In production you'd send streamed tokens to the browser via **Server-Sent Events (SSE)** or **WebSockets**:

```python
# FastAPI example
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.get("/chat")
async def chat(question: str):
    async def generate():
        async for chunk, _ in agent.astream(
            input={"messages": [{"role": "user", "content": question}]},
            stream_mode="messages",
        ):
            if hasattr(chunk, "content") and chunk.content:
                # Send each token as an SSE event
                yield f"data: {chunk.content}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## ▶️ How to Run

```bash
python 05_streaming/agent.py
```

### Expected Output

```
⚡ Streaming Agent Demo

📍 Demo 1: Basic streaming
👤 User: Tell me a joke about programmers, then calculate 144 / 12 * 7
🤖 Agent:
   🔧 [calling tool: get_joke]
   🔧 [calling tool: calculate]

Sure! Here's a joke for you:

**Why do programmers prefer dark mode?**
Because light attracts bugs! 🐛

And for your calculation:
144 / 12 * 7 = **84** ✅
```

---

## ➡️ Next Steps

- **[06 — Human in the Loop](../06_human_in_loop/)** — pause the agent mid-task and ask a human to approve before continuing
