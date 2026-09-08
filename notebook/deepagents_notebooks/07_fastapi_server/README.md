# 07 — FastAPI Server: Your Agent as a REST API

> **Difficulty:** ⭐⭐⭐ Intermediate

Every previous example runs as a one-off script. In production, your agent needs to be a **server** — always running, accepting requests from web apps, mobile apps, and other services. This example wraps your agent in a FastAPI REST API with streaming support.

---

## 🎯 What You'll Learn

- How to expose a Deep Agent as a **REST API**
- How to handle **multi-turn conversations** via session IDs
- How to stream responses using **Server-Sent Events (SSE)**
- How to build proper **request/response models** with Pydantic
- How to run the server with **uvicorn**

---

## 📂 Files

```
07_fastapi_server/
├── server.py     # FastAPI app with 6 endpoints
└── README.md     # This file
```

---

## 🌐 API Endpoints

| Method | Endpoint | What it does |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/chat` | Send message, get full response |
| `GET` | `/chat/stream` | Send message, get streaming response |
| `GET` | `/history/{session_id}` | Get conversation history |
| `DELETE` | `/history/{session_id}` | Clear conversation history |
| `GET` | `/sessions` | List all active sessions |

---

## ⚙️ Setup

```bash
pip install fastapi uvicorn deepagents
export ANTHROPIC_API_KEY="your-key"
```

---

## ▶️ How to Run

```bash
python 07_fastapi_server/server.py
```

You'll see:
```
🚀 Deep Agents FastAPI Server
📡 Endpoints:
   POST   http://localhost:8000/chat
   GET    http://localhost:8000/chat/stream
   ...
📖 Docs: http://localhost:8000/docs
```

FastAPI auto-generates interactive docs at **http://localhost:8000/docs** — open that in your browser to test every endpoint with a UI.

---

## 🧪 Testing the API

### Basic chat

```bash
curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "What is the weather in Rome?", "session_id": "user_001"}'
```

Response:
```json
{
  "response": "The weather in Rome is sunny and 22°C.",
  "session_id": "user_001",
  "message_count": 2
}
```

### Streaming chat

```bash
curl "http://localhost:8000/chat/stream?message=Tell+me+a+fact+about+AI&session_id=user_001"
```

Response (tokens arrive one by one):
```
data: {"token": "Did", "session_id": "user_001"}
data: {"token": " you", "session_id": "user_001"}
data: {"token": " know", "session_id": "user_001"}
...
data: {"token": "[DONE]", "session_id": "user_001", "message_count": 4}
```

### Multi-turn conversation (agent remembers context)

```bash
# Message 1
curl -X POST http://localhost:8000/chat \
     -d '{"message": "My name is Marco", "session_id": "user_001"}'

# Message 2 — agent remembers "Marco" from the session history
curl -X POST http://localhost:8000/chat \
     -d '{"message": "What is my name?", "session_id": "user_001"}'
# → "Your name is Marco!"
```

### Get conversation history

```bash
curl http://localhost:8000/history/user_001
```

---

## 🔑 Key Code Patterns

### Session-based conversation history

```python
session_store: dict[str, list] = defaultdict(list)

@app.post("/chat")
def chat(request: ChatRequest):
    sid = request.session_id or str(uuid.uuid4())

    # Add user message to history
    session_store[sid].append({"role": "user", "content": request.message})

    # Invoke agent with FULL history (gives it conversation context)
    result = agent.invoke({"messages": session_store[sid]})
    response = result["messages"][-1].content

    # Save agent's reply to history
    session_store[sid].append({"role": "assistant", "content": response})
```

### SSE Streaming

```python
@app.get("/chat/stream")
def chat_stream(message: str):
    def generate():
        for chunk, _ in agent.stream(input={...}, stream_mode="messages"):
            if chunk.content:
                yield f"data: {json.dumps({'token': chunk.content})}\n\n"
        yield "data: {\"token\": \"[DONE]\"}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## 🌍 Connecting a Frontend

### JavaScript (fetch + SSE)

```javascript
// Regular chat
const res = await fetch("http://localhost:8000/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: "Hello!", session_id: "user_001" })
});
const data = await res.json();
console.log(data.response);

// Streaming chat
const source = new EventSource(
  "http://localhost:8000/chat/stream?message=Hello&session_id=user_001"
);
source.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.token === "[DONE]") {
    source.close();
  } else {
    document.getElementById("output").innerText += data.token;
  }
};
```

---

## 🚀 Production Checklist

Before deploying to production:

- [ ] Replace in-memory `session_store` with **Redis** or **PostgreSQL**
- [ ] Add **authentication** (API keys, JWT tokens)
- [ ] Restrict CORS to your actual frontend domain
- [ ] Add **rate limiting** to prevent abuse
- [ ] Set up **logging** and monitoring
- [ ] Use **HTTPS** (not HTTP)
- [ ] Deploy with **gunicorn** + multiple workers: `gunicorn server:app -w 4 -k uvicorn.workers.UvicornWorker`

---

## ➡️ You've completed all examples! 🎉

Suggested next steps:
- [LangSmith](https://smith.langchain.com/) — trace and debug your agents visually
- [LangGraph Platform](https://docs.langchain.com/oss/python/langgraph/deploy) — managed deployment for LangGraph agents
- [Deep Agents Backends](https://docs.langchain.com/oss/python/deepagents/backends) — production file storage
