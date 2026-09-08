# ============================================================
# Example 05: Streaming Agent — Real-Time Token Output
# ============================================================
#
# By default agent.invoke() waits for the ENTIRE response before
# returning it. For long responses this feels slow and unresponsive.
#
# STREAMING lets you print tokens as they arrive — just like
# ChatGPT's typing effect. This is essential for production UIs.
#
# Deep Agents support streaming via agent.stream() which yields
# events as they happen:
#   - "on_chat_model_stream"  → a new token arrived from the LLM
#   - "on_tool_start"         → agent is about to call a tool
#   - "on_tool_end"           → tool finished, result ready
#
# Run this file:
#   python 05_streaming/agent.py
# ============================================================

import os
import sys
import time
from deepagents import create_deep_agent


# ── TOOLS ─────────────────────────────────────────────────────

def get_joke(topic: str) -> str:
    """
    Get a funny joke about a given topic.

    Args:
        topic: The subject of the joke (e.g. "programmers", "AI", "cats")

    Returns:
        A joke string.
    """
    # Hardcoded jokes for demo — in real life call a jokes API
    jokes = {
        "programmers": "Why do programmers prefer dark mode? Because light attracts bugs!",
        "ai": "Why did the AI go to therapy? It had too many deep issues.",
        "cats": "Why don't cats play poker in the jungle? Too many cheetahs.",
        "python": "Why do Python programmers wear glasses? Because they can't C#.",
    }
    # Return specific joke or a default
    return jokes.get(topic.lower(), f"Why did the {topic} cross the road? To get to the other side!")


def calculate(expression: str) -> str:
    """
    Safely evaluate a mathematical expression and return the result.

    Args:
        expression: A math expression string (e.g. "2 + 2", "15 * 7 / 3")

    Returns:
        The result as a string, or an error message.
    """
    try:
        # Only allow safe math characters to prevent code injection
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return f"Error: expression contains invalid characters"

        result = eval(expression)  # Safe because we validated characters above
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error calculating '{expression}': {e}"


# ── CREATE AGENT ──────────────────────────────────────────────

agent = create_deep_agent(
    tools=[get_joke, calculate],
    system_prompt="""You are a fun and friendly assistant who loves telling jokes
and helping with math. You explain your thinking step by step.
When asked multiple things, address each one clearly and fully.""",
)


# ── STREAMING HELPER ──────────────────────────────────────────

def stream_response(question: str, show_tool_calls: bool = True) -> None:
    """
    Stream the agent's response, printing tokens as they arrive.

    This gives the user a real-time "typing" experience instead of
    waiting for the full response before anything is shown.

    Args:
        question: The user's question/message
        show_tool_calls: If True, shows when the agent uses a tool
    """
    print(f"\n👤 User: {question}")
    print(f"🤖 Agent: ", end="", flush=True)

    # agent.stream() yields events as they happen
    # We use astream_events for detailed event-level streaming
    for chunk in agent.stream(
        input={"messages": [{"role": "user", "content": question}]},
        # stream_mode="messages" gives us token-by-token output
        stream_mode="messages",
    ):
        # chunk is a tuple: (message_chunk, metadata)
        message_chunk, metadata = chunk

        # Check if this chunk has text content (it might be a tool call chunk)
        if hasattr(message_chunk, "content") and message_chunk.content:
            content = message_chunk.content

            # content can be a string or a list of content blocks
            if isinstance(content, str):
                # Print the token immediately without newline
                print(content, end="", flush=True)

            elif isinstance(content, list):
                # Handle list of content blocks (some models return this format)
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        print(block.get("text", ""), end="", flush=True)

        # If it's a tool call, optionally show it
        elif show_tool_calls and hasattr(message_chunk, "tool_calls"):
            if message_chunk.tool_calls:
                for tool_call in message_chunk.tool_calls:
                    tool_name = tool_call.get("name", "")
                    if tool_name:
                        print(f"\n   🔧 [calling tool: {tool_name}]", end="", flush=True)

    # Newline after the full response
    print("\n")


def stream_with_events(question: str) -> None:
    """
    Alternative streaming mode that shows all events in detail.

    This is useful for debugging — you can see every step the agent takes:
    tool calls, tool results, and each token as it's generated.

    Args:
        question: The user's question/message
    """
    print(f"\n👤 User: {question}")
    print("─" * 40)

    for event in agent.astream_events(
        input={"messages": [{"role": "user", "content": question}]},
        version="v2",  # Use the latest event format
    ):
        event_name = event.get("event", "")
        event_data = event.get("data", {})

        # A new token arrived from the LLM
        if event_name == "on_chat_model_stream":
            chunk = event_data.get("chunk", {})
            if hasattr(chunk, "content") and chunk.content:
                print(chunk.content, end="", flush=True)

        # The agent is about to call a tool
        elif event_name == "on_tool_start":
            tool_name = event.get("name", "unknown")
            tool_input = event_data.get("input", {})
            print(f"\n\n   🔧 Tool call: {tool_name}({tool_input})")
            print("   ⏳ Running...", end="", flush=True)

        # A tool finished running
        elif event_name == "on_tool_end":
            tool_output = event_data.get("output", "")
            print(f" → {str(tool_output)[:100]}")  # Show first 100 chars of result
            print("\n🤖 Agent (continuing): ", end="", flush=True)

    print("\n" + "─" * 40)


# ── INVOKE vs STREAM COMPARISON ───────────────────────────────

def compare_invoke_vs_stream(question: str) -> None:
    """
    Demonstrates the difference between invoke() and stream().

    invoke() → waits for everything, then prints all at once
    stream() → prints tokens as they arrive (much better UX)
    """
    print("\n" + "=" * 60)
    print("📊 Comparing invoke() vs stream()")
    print("=" * 60)

    # ── Method 1: invoke (waits for full response) ──────────
    print("\n1️⃣  Using invoke() — waits for full response:")
    print("   (Notice the delay before anything appears...)")
    start = time.time()
    result = agent.invoke({
        "messages": [{"role": "user", "content": question}]
    })
    elapsed = time.time() - start
    response = result["messages"][-1].content
    print(f"   Response arrived after {elapsed:.1f}s:")
    print(f"   {response[:200]}...")

    # ── Method 2: stream (tokens appear immediately) ─────────
    print(f"\n2️⃣  Using stream() — tokens appear immediately:")
    print("   (Notice how text starts appearing right away...)\n")
    print("   🤖 Agent: ", end="", flush=True)
    start = time.time()
    first_token_time = None

    for chunk, metadata in agent.stream(
        input={"messages": [{"role": "user", "content": question}]},
        stream_mode="messages",
    ):
        if hasattr(chunk, "content") and chunk.content:
            if first_token_time is None:
                first_token_time = time.time() - start
            if isinstance(chunk.content, str):
                print(chunk.content, end="", flush=True)

    print(f"\n\n   First token appeared after: {first_token_time:.1f}s")
    print("   Full response streamed token by token ✅")


# ── DEMO ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("⚡ Streaming Agent Demo")
    print("=" * 60)

    # Demo 1: Basic streaming — watch tokens appear in real time
    print("\n📍 Demo 1: Basic streaming")
    stream_response(
        "Tell me a joke about programmers, then calculate 144 / 12 * 7 for me.",
        show_tool_calls=True,
    )

    # Demo 2: Longer response — streaming really shines here
    print("\n📍 Demo 2: Longer response (streaming shows its value)")
    stream_response(
        "Explain the difference between invoke() and stream() in LangChain agents. "
        "Give me 3 specific use cases where streaming is important, "
        "and 2 where invoke() is fine. Be thorough.",
        show_tool_calls=False,
    )

    # Demo 3: Multiple tool calls streamed
    print("\n📍 Demo 3: Multiple tool calls")
    stream_response(
        "Tell me 3 jokes: one about AI, one about cats, and one about Python. "
        "Also calculate 2024 / 8 and tell me what you get.",
        show_tool_calls=True,
    )

    print("=" * 60)
    print("✅ Streaming demo complete!")
    print("   In production: connect stream() to WebSockets or SSE")
    print("   to push tokens directly to your frontend UI.")
    print("=" * 60)
