# ============================================================
# Example 07: FastAPI Server — Your Agent as a REST API
# ============================================================
#
# So far every example runs as a Python script you execute once.
# In production, your agent needs to be a SERVER that can:
#   - Accept requests from web apps, mobile apps, other services
#   - Handle multiple users simultaneously
#   - Stream responses to the client in real time
#   - Maintain conversation history per user/session
#
# This example wraps a Deep Agent in a FastAPI server with:
#   - POST /chat        → standard request/response (no streaming)
#   - GET  /chat/stream → streaming response (tokens sent as SSE)
#   - GET  /history     → retrieve conversation history
#   - DELETE /history   → clear conversation history
#   - GET  /health      → server health check
#
# Install FastAPI:
#   pip install fastapi uvicorn
#
# Run the server:
#   python 07_fastapi_server/server.py
#   # Server runs at http://localhost:8000
#
# Test it:
#   curl -X POST http://localhost:8000/chat \
#        -H "Content-Type: application/json" \
#        -d '{"message": "What is 2+2?", "session_id": "user123"}'
# ============================================================

import os
import uuid
import json
import asyncio
from typing import Optional
from collections import defaultdict

# FastAPI imports
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("❌ FastAPI not installed. Run: pip install fastapi uvicorn")
    exit(1)

from deepagents import create_deep_agent


# ── TOOLS ─────────────────────────────────────────────────────

def get_weather(city: str) -> str:
    """
    Get the current weather for a given city.

    Args:
        city: Name of the city

    Returns:
        A weather description string.
    """
    return f"The weather in {city} is sunny and 22°C."


def calculate(expression: str) -> str:
    """
    Safely evaluate a mathematical expression.

    Args:
        expression: Math expression like "2 + 2" or "15 * 7"

    Returns:
        The calculated result.
    """
    try:
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expression):
            return "Error: invalid characters in expression"
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {e}"


def get_fact(topic: str) -> str:
    """
    Get an interesting fact about a topic.

    Args:
        topic: The topic to get a fact about

    Returns:
        An interesting fact.
    """
    facts = {
        "python": "Python was named after Monty Python, not the snake.",
        "internet": "The first website went live on August 6, 1991.",
        "ai": "The term 'Artificial Intelligence' was coined in 1956 by John McCarthy.",
        "space": "One day on Venus is longer than one year on Venus.",
    }
    return facts.get(topic.lower(), f"Did you know? {topic} is a fascinating subject!")


# ── CREATE THE AGENT ──────────────────────────────────────────

agent = create_deep_agent(
    tools=[get_weather, calculate, get_fact],
    system_prompt="""You are a friendly, helpful AI assistant accessible via API.
You can check weather, do calculations, and share interesting facts.
Be concise but thorough. Always use the available tools when relevant.""",
)

# ── SESSION STORE ─────────────────────────────────────────────
#
# We keep conversation history per session so the agent remembers
# previous messages within the same conversation.
#
# In production, use Redis or a database instead of in-memory storage.

session_store: dict[str, list] = defaultdict(list)


# ── FASTAPI APP ───────────────────────────────────────────────

app = FastAPI(
    title="Deep Agents API",
    description="A REST API wrapping a LangChain Deep Agent",
    version="1.0.0",
)

# Allow cross-origin requests (needed for browser-based frontends)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # In production: restrict to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REQUEST / RESPONSE MODELS ─────────────────────────────────
#
# Pydantic models define the shape of API request and response bodies.
# FastAPI uses them for automatic validation and documentation.

class ChatRequest(BaseModel):
    """Request body for the /chat endpoint."""
    message: str                          # The user's message
    session_id: Optional[str] = None      # Optional: link to a conversation session


class ChatResponse(BaseModel):
    """Response body from the /chat endpoint."""
    response: str                          # The agent's reply
    session_id: str                        # The session ID (auto-generated if not provided)
    message_count: int                     # Total messages in this session


class HistoryResponse(BaseModel):
    """Response body from the /history endpoint."""
    session_id: str
    messages: list
    message_count: int


# ── ENDPOINTS ─────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """
    Health check endpoint.
    Returns 200 OK if the server is running.
    """
    return {"status": "healthy", "agent": "running"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Send a message to the agent and get a response.

    This is a standard request/response endpoint — it waits for the
    full response before returning. Use /chat/stream for real-time output.

    Example:
        curl -X POST http://localhost:8000/chat \\
             -H "Content-Type: application/json" \\
             -d '{"message": "What is the weather in Paris?", "session_id": "user_001"}'
    """
    # Generate a session ID if not provided
    session_id = request.session_id or str(uuid.uuid4())

    # Add the new user message to the session history
    session_store[session_id].append({
        "role": "user",
        "content": request.message,
    })

    try:
        # Invoke the agent with the FULL conversation history
        # This gives the agent context of previous messages
        result = agent.invoke({
            "messages": session_store[session_id]
        })

        # Extract the agent's response
        agent_response = result["messages"][-1].content

        # Save the agent's response to session history
        session_store[session_id].append({
            "role": "assistant",
            "content": agent_response,
        })

        return ChatResponse(
            response=agent_response,
            session_id=session_id,
            message_count=len(session_store[session_id]),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@app.get("/chat/stream")
def chat_stream(message: str, session_id: Optional[str] = None):
    """
    Stream the agent's response token by token using Server-Sent Events (SSE).

    This gives users a real-time "typing" experience.

    Example:
        curl "http://localhost:8000/chat/stream?message=Tell+me+a+fact+about+AI&session_id=user_001"

    SSE format: each event is sent as:
        data: <token>\\n\\n

    The stream ends with:
        data: [DONE]\\n\\n
    """
    # Generate a session ID if not provided
    sid = session_id or str(uuid.uuid4())

    # Add user message to history
    session_store[sid].append({
        "role": "user",
        "content": message,
    })

    # Collect the full response to save to history after streaming
    full_response = []

    def generate():
        """Generator function that yields SSE events."""
        try:
            # Stream the agent's response
            for chunk, metadata in agent.stream(
                input={"messages": session_store[sid]},
                stream_mode="messages",
            ):
                # Check if this chunk has text content
                if hasattr(chunk, "content") and chunk.content:
                    token = chunk.content

                    # Handle string content
                    if isinstance(token, str) and token:
                        full_response.append(token)
                        # SSE format: "data: <content>\n\n"
                        yield f"data: {json.dumps({'token': token, 'session_id': sid})}\n\n"

                    # Handle list content (some models)
                    elif isinstance(token, list):
                        for block in token:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "")
                                if text:
                                    full_response.append(text)
                                    yield f"data: {json.dumps({'token': text, 'session_id': sid})}\n\n"

            # Save the complete response to session history
            complete_response = "".join(full_response)
            session_store[sid].append({
                "role": "assistant",
                "content": complete_response,
            })

            # Send the "done" signal
            yield f"data: {json.dumps({'token': '[DONE]', 'session_id': sid, 'message_count': len(session_store[sid])})}\n\n"

        except Exception as e:
            # Send the error as an SSE event
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
        },
    )


@app.get("/history/{session_id}", response_model=HistoryResponse)
def get_history(session_id: str):
    """
    Get the conversation history for a session.

    Example:
        curl http://localhost:8000/history/user_001
    """
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    return HistoryResponse(
        session_id=session_id,
        messages=session_store[session_id],
        message_count=len(session_store[session_id]),
    )


@app.delete("/history/{session_id}")
def clear_history(session_id: str):
    """
    Clear the conversation history for a session.

    Example:
        curl -X DELETE http://localhost:8000/history/user_001
    """
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    del session_store[session_id]
    return {"message": f"History cleared for session '{session_id}'"}


@app.get("/sessions")
def list_sessions():
    """
    List all active session IDs.

    Example:
        curl http://localhost:8000/sessions
    """
    return {
        "sessions": list(session_store.keys()),
        "total": len(session_store),
    }


# ── RUN THE SERVER ────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Deep Agents FastAPI Server")
    print("=" * 60)
    print("\n📡 Endpoints:")
    print("   POST   http://localhost:8000/chat          ← Send message")
    print("   GET    http://localhost:8000/chat/stream   ← Stream response")
    print("   GET    http://localhost:8000/history/{id}  ← Get history")
    print("   DELETE http://localhost:8000/history/{id}  ← Clear history")
    print("   GET    http://localhost:8000/sessions      ← List sessions")
    print("   GET    http://localhost:8000/health        ← Health check")
    print("\n📖 Docs: http://localhost:8000/docs")
    print("=" * 60)

    # Start the server
    uvicorn.run(
        app,
        host="0.0.0.0",   # Listen on all interfaces
        port=8000,
        reload=False,      # Set to True during development for auto-reload
    )
