# ============================================================
# Example 01: Hello World — Your First Deep Agent
# ============================================================
#
# This is the simplest possible Deep Agent example.
# It shows the three core building blocks:
#   1. A TOOL  — a Python function the agent can call
#   2. AN AGENT — the AI brain created with create_deep_agent()
#   3. AN INVOKE — running the agent with a user message
#
# Run this file:
#   python 01_hello_world/agent.py
# ============================================================

import os
from deepagents import create_deep_agent

# ── STEP 1: Define your tools ────────────────────────────────
#
# A "tool" is just a regular Python function.
# The agent reads the docstring to understand WHAT the tool does
# and the type hints to understand WHAT arguments to pass.
#
# You don't need to call these functions yourself —
# the agent decides WHEN and HOW to call them automatically.

def get_weather(city: str) -> str:
    """
    Get the current weather for a given city.

    Args:
        city: The name of the city to get weather for (e.g. "Rome", "Paris")

    Returns:
        A string describing the current weather in that city.
    """
    # In a real app you'd call a weather API here (e.g. OpenWeatherMap).
    # For this demo we return a hardcoded sunny response.
    return f"The weather in {city} is currently sunny and 24°C. Perfect day to go outside!"


def get_time(city: str) -> str:
    """
    Get the current local time for a given city.

    Args:
        city: The name of the city to get the local time for.

    Returns:
        A string with the current local time in that city.
    """
    # In a real app you'd use pytz or a time zone API here.
    # For demo purposes we return a fixed time.
    return f"The current local time in {city} is 14:35 (2:35 PM)."


def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """
    Convert an amount from one currency to another.

    Args:
        amount: The numeric amount to convert (e.g. 100.0)
        from_currency: The source currency code (e.g. "USD", "EUR")
        to_currency: The target currency code (e.g. "GBP", "JPY")

    Returns:
        A string with the converted amount.
    """
    # Hardcoded exchange rates for demo purposes.
    # In a real app you'd call a currency API (e.g. exchangerate.host).
    rates = {
        ("USD", "EUR"): 0.92,
        ("EUR", "USD"): 1.09,
        ("USD", "GBP"): 0.79,
        ("GBP", "USD"): 1.27,
        ("EUR", "GBP"): 0.86,
        ("GBP", "EUR"): 1.16,
    }

    key = (from_currency.upper(), to_currency.upper())
    rate = rates.get(key)

    if rate is None:
        return f"Sorry, I don't have the exchange rate for {from_currency} → {to_currency}."

    converted = amount * rate
    return f"{amount} {from_currency} = {converted:.2f} {to_currency} (rate: {rate})"


# ── STEP 2: Create the agent ──────────────────────────────────
#
# create_deep_agent() is the main function from the deepagents library.
# It wires together:
#   - An LLM (Claude by default if ANTHROPIC_API_KEY is set)
#   - Your tools (passed as a list)
#   - A system prompt (instructions that define the agent's personality/role)
#   - Built-in capabilities: planning (write_todos), file system, subagents

agent = create_deep_agent(
    # Pass the list of tools the agent is allowed to use.
    # The agent will automatically decide which tool to call based on the user's question.
    tools=[get_weather, get_time, convert_currency],

    # The system prompt is like a job description for your agent.
    # It tells the agent who it is, what it can do, and how to behave.
    system_prompt="""You are a friendly travel assistant. 
    
You help users with:
- Current weather at their destination
- Local time at their destination  
- Currency conversion for their trip

Always be friendly and helpful. When answering, use the tools available to get accurate information.
If the user asks about multiple things, answer all of them in a single, well-organized response.
""",
)

# ── STEP 3: Run the agent ─────────────────────────────────────
#
# agent.invoke() sends a message to the agent and waits for the full response.
# The input is a dict with a "messages" key containing a list of messages.
# Each message has a "role" (user/assistant) and "content" (the text).

def ask(question: str) -> str:
    """Helper function to ask the agent a question and return its answer."""
    result = agent.invoke({
        "messages": [
            {"role": "user", "content": question}
        ]
    })
    # The agent's final response is always the last message in the list
    return result["messages"][-1].content


# ── DEMO: Ask the agent some questions ───────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 Hello World Deep Agent")
    print("=" * 60)

    # Question 1: Simple single-tool call
    print("\n📍 Question 1: Weather")
    print("-" * 40)
    answer1 = ask("What's the weather like in Rome today?")
    print(answer1)

    # Question 2: Another single-tool call
    print("\n📍 Question 2: Time")
    print("-" * 40)
    answer2 = ask("What time is it in Tokyo right now?")
    print(answer2)

    # Question 3: Multi-tool call — the agent uses multiple tools in one response
    print("\n📍 Question 3: Multi-tool (weather + time + currency)")
    print("-" * 40)
    answer3 = ask(
        "I'm planning a trip to Paris. "
        "What's the weather there, what time is it, "
        "and how much is 200 USD in EUR?"
    )
    print(answer3)

    print("\n" + "=" * 60)
    print("✅ Done! The agent used your tools to answer each question.")
    print("=" * 60)
