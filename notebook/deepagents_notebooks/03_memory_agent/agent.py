# ============================================================
# Example 03: Memory Agent — Remembering Users Across Sessions
# ============================================================
#
# By default, every time you call agent.invoke(), the agent starts
# fresh — it has no memory of previous conversations.
#
# This example shows how to add LONG-TERM MEMORY so the agent:
#   - Remembers user preferences (name, location, interests)
#   - Recalls facts from previous conversations
#   - Personalizes responses based on what it knows about you
#
# Deep Agents use LangGraph's Memory Store for persistence.
# Memory is stored in a checkpointer (SQLite here for simplicity,
# but you can use Redis or Postgres in production).
#
# Run this file:
#   python 03_memory_agent/agent.py
# ============================================================

import os
import uuid
from deepagents import create_deep_agent

# ── UNDERSTANDING THREADS ─────────────────────────────────────
#
# LangGraph uses the concept of "threads" to manage conversations.
# A thread_id groups messages together into one conversation session.
#
# Same thread_id  → agent remembers previous messages in this session
# Different thread_id → new session, but long-term memory still persists
#
# Think of thread_id like a "conversation ID" in a chat app.

# A fixed user ID so we can simulate the same user coming back
USER_ID = "user_001"

# ── TOOL: Save a memory ───────────────────────────────────────
#
# We give the agent an explicit tool to save important information
# about the user. In a real app, you might also auto-extract memories
# using LangGraph's built-in memory features.

def remember_user_info(key: str, value: str) -> str:
    """
    Save an important piece of information about the user to long-term memory.

    Use this tool whenever the user tells you something important about
    themselves that you should remember for future conversations.

    Examples of things worth remembering:
    - User's name
    - User's location/city
    - User's job or profession
    - User's hobbies and interests
    - User's preferences (e.g. prefers metric units, vegetarian)
    - Important facts the user has shared

    Args:
        key: A short label for what you're saving (e.g. "name", "city", "hobby")
        value: The information to save (e.g. "Maria", "Rome", "photography")

    Returns:
        Confirmation that the memory was saved.
    """
    # In this simplified demo, we save to a local JSON file.
    # In production you'd use LangGraph's Memory Store (backed by
    # Redis, Postgres, or another persistent store).
    import json

    memory_file = f"memory_{USER_ID}.json"

    # Load existing memories if any
    if os.path.exists(memory_file):
        with open(memory_file, "r") as f:
            memories = json.load(f)
    else:
        memories = {}

    # Save the new key-value pair
    memories[key] = value

    with open(memory_file, "w") as f:
        json.dump(memories, f, indent=2)

    return f"✅ Remembered: {key} = '{value}'"


def recall_user_info(key: str = None) -> str:
    """
    Retrieve information previously saved about the user from long-term memory.

    Use this at the start of conversations or when you need to recall
    something specific about the user.

    Args:
        key: The specific piece of info to recall (e.g. "name", "city").
             If None or empty, returns ALL saved information about the user.

    Returns:
        The saved information, or a message saying nothing was found.
    """
    import json

    memory_file = f"memory_{USER_ID}.json"

    if not os.path.exists(memory_file):
        return "No memories saved for this user yet."

    with open(memory_file, "r") as f:
        memories = json.load(f)

    if not memories:
        return "No memories saved for this user yet."

    # Return a specific key if requested
    if key and key in memories:
        return f"{key}: {memories[key]}"

    # Otherwise return all memories as a formatted string
    if key and key not in memories:
        return f"No memory found for key '{key}'."

    # Return all memories formatted nicely
    lines = [f"  • {k}: {v}" for k, v in memories.items()]
    return "Everything I know about this user:\n" + "\n".join(lines)


def forget_user_info(key: str) -> str:
    """
    Delete a specific piece of information from the user's memory.

    Use this when the user asks you to forget something or when
    stored information is no longer accurate.

    Args:
        key: The key of the memory to delete (e.g. "old_city")

    Returns:
        Confirmation that the memory was deleted.
    """
    import json

    memory_file = f"memory_{USER_ID}.json"

    if not os.path.exists(memory_file):
        return "No memories exist to delete."

    with open(memory_file, "r") as f:
        memories = json.load(f)

    if key not in memories:
        return f"No memory found for key '{key}'."

    del memories[key]

    with open(memory_file, "w") as f:
        json.dump(memories, f, indent=2)

    return f"🗑️ Deleted memory: '{key}'"


# ── SYSTEM PROMPT ─────────────────────────────────────────────
#
# The key addition here is explicit instructions to:
#   1. Recall memories at the start of each conversation
#   2. Save new information whenever the user shares it
#   3. Use memories to personalize responses

MEMORY_SYSTEM_PROMPT = """You are a personal AI assistant with long-term memory.

## Your Memory Instructions

At the START of every conversation:
- Always call recall_user_info() to load what you know about this user
- Greet the user by name if you know it
- Reference relevant past context naturally (don't be robotic about it)

During the conversation:
- When the user tells you something personal (name, city, job, hobby, preference),
  IMMEDIATELY call remember_user_info() to save it
- When the user says "remember that..." or "don't forget...", always save it
- When the user says "forget that..." or "that's wrong...", use forget_user_info()

PERSONALIZE your responses:
- Use the user's name when you know it
- Reference their location for relevant questions
- Tailor advice to their known profession or interests

Be natural about using memories — don't announce "I'm saving your info". 
Just do it silently and respond naturally.
"""

# ── CREATE THE AGENT ──────────────────────────────────────────
#
# We pass the memory tools alongside the system prompt.
# The agent automatically gets write_todos and file system tools too.

agent = create_deep_agent(
    tools=[remember_user_info, recall_user_info, forget_user_info],
    system_prompt=MEMORY_SYSTEM_PROMPT,
)


# ── CONVERSATION SIMULATOR ───────────────────────────────────
#
# To simulate "different sessions", we use different thread_ids.
# In a real app, thread_id would be a unique session/conversation ID.

def chat(message: str, thread_id: str = "session_1") -> str:
    """
    Send a message to the memory agent.

    Args:
        message: What the user says
        thread_id: Unique ID for this conversation session.
                   Same thread_id = same conversation context.
                   Different thread_id = new session (but long-term memory persists).

    Returns:
        The agent's response.
    """
    result = agent.invoke(
        input={"messages": [{"role": "user", "content": message}]},
        # config is how LangGraph knows which thread this belongs to
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].content


# ── DEMO ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🧠 Memory Agent Demo")
    print("=" * 60)

    # ── SESSION 1: User introduces themselves
    print("\n📅 SESSION 1 — First time talking to the agent")
    print("-" * 40)

    response1 = chat(
        "Hi! My name is Marco. I live in Rome and I'm a software engineer. "
        "I love cooking Italian food in my spare time.",
        thread_id="session_001"
    )
    print(f"User: Hi! My name is Marco. I live in Rome...")
    print(f"Agent: {response1}")

    response2 = chat(
        "I prefer Celsius for temperatures and I'm vegetarian.",
        thread_id="session_001"
    )
    print(f"\nUser: I prefer Celsius for temperatures and I'm vegetarian.")
    print(f"Agent: {response2}")

    # ── SESSION 2: New session — agent should remember Marco
    print("\n\n📅 SESSION 2 — New session (different thread_id)")
    print("-" * 40)
    print("(Simulating coming back the next day with a new session ID)\n")

    response3 = chat(
        "Hello again!",
        thread_id="session_002"  # ← New session ID, but memory persists
    )
    print(f"User: Hello again!")
    print(f"Agent: {response3}")

    response4 = chat(
        "What's a good recipe I could cook this weekend?",
        thread_id="session_002"
    )
    print(f"\nUser: What's a good recipe I could cook this weekend?")
    print(f"Agent: {response4}")

    # ── SESSION 3: User updates their info
    print("\n\n📅 SESSION 3 — User updates information")
    print("-" * 40)

    response5 = chat(
        "I moved to Milan last month. Please update that.",
        thread_id="session_003"
    )
    print(f"User: I moved to Milan last month. Please update that.")
    print(f"Agent: {response5}")

    response6 = chat(
        "Also, please forget that I'm vegetarian — I eat meat now.",
        thread_id="session_003"
    )
    print(f"\nUser: Also, please forget that I'm vegetarian...")
    print(f"Agent: {response6}")

    print("\n" + "=" * 60)
    print("✅ Demo complete! The agent remembered Marco across all 3 sessions.")
    print(f"   Memories saved to: memory_{USER_ID}.json")
    print("=" * 60)
