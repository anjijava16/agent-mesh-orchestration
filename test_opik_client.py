"""
Test script to send dummy traces to Opik.
Run this from your local machine (not inside Docker).

Usage:
    python test_opik_client.py
"""
import os
import time

# Point Opik SDK at the self-hosted backend (exposed on port 8083)
os.environ["OPIK_URL_OVERRIDE"] = "http://localhost:5174"
os.environ["OPIK_PROJECT_NAME"] = "AgentMesh-Test"

import opik

# Configure for self-hosted
opik.configure(url="http://localhost:5174", use_local=True)

client = opik.Opik(project_name="AgentMesh-Test")

print("=" * 60)
print("Sending dummy traces to Opik...")
print(f"URL: http://localhost:5174")
print(f"Project: AgentMesh-Test")
print("=" * 60)

# --- Trace 1: Simple LLM call ---
print("\n1. Logging a simple LLM call trace...")
trace1 = client.trace(
    name="langgraph/claude-sonnet-4-6",
    input={"message": "What is machine learning?"},
    output={"answer": "Machine learning is a subset of AI that enables systems to learn from data..."},
    metadata={
        "framework": "langgraph",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "conversation_id": "test-conv-001",
        "run_id": "test-run-001",
        "duration_ms": 2500,
        "total_tokens": 1250,
    },
    tags=["langgraph", "anthropic", "test"],
)
trace1.span(
    name="orchestrator/plan",
    input={"plan": ["researcher", "retriever", "writer"]},
    output={"summary": "Routing to researcher first"},
    metadata={"agent": "orchestrator", "step_index": 0},
)
trace1.span(
    name="researcher/web_search",
    input={"tool": "web_search", "query": "machine learning definition"},
    output={"output": '{"results": [{"title": "ML Overview", "url": "https://example.com"}]}'},
    metadata={"agent": "researcher", "step_index": 1, "duration_ms": 1200},
)
trace1.span(
    name="writer/agent_finished",
    input={"context": "Research findings about ML..."},
    output={"summary": "Machine learning is a subset of AI..."},
    metadata={"agent": "writer", "step_index": 2, "duration_ms": 800},
)
print(f"   Trace ID: {trace1.id}")

# --- Trace 2: Tool-heavy trace ---
print("\n2. Logging a tool-heavy trace (ADK runtime)...")
trace2 = client.trace(
    name="google_adk/gemini-2.5-flash",
    input={"message": "Search for latest Python news and summarize"},
    output={"answer": "Here are the latest Python developments: Python 3.14 beta released..."},
    metadata={
        "framework": "google_adk",
        "provider": "google",
        "model": "gemini-2.5-flash",
        "conversation_id": "test-conv-002",
        "run_id": "test-run-002",
        "duration_ms": 8500,
        "total_tokens": 3200,
    },
    tags=["google_adk", "google", "test"],
)
trace2.span(
    name="researcher/web_search",
    input={"tool": "web_search", "query": "Python programming news 2026"},
    output={"output": '{"results": [{"title": "Python 3.14 Released"}]}'},
    metadata={"agent": "researcher", "duration_ms": 2100},
)
trace2.span(
    name="retriever/hybrid_search",
    input={"tool": "hybrid_search", "query": "Python updates"},
    output={"output": '{"passages": []}'},
    metadata={"agent": "retriever", "duration_ms": 450},
)
trace2.span(
    name="analyst/calculator",
    input={"tool": "calculator", "expression": "3.14 * 2"},
    output={"output": '{"result": 6.28}'},
    metadata={"agent": "analyst", "duration_ms": 50},
)
trace2.span(
    name="compliance/pii_scan",
    input={"tool": "pii_scan", "text": "No PII here"},
    output={"output": '{"clean": true}'},
    metadata={"agent": "compliance", "duration_ms": 30},
)
trace2.span(
    name="writer/agent_finished",
    input={"research": "Python 3.14 info..."},
    output={"summary": "Here are the latest Python developments..."},
    metadata={"agent": "writer", "duration_ms": 1500},
)
print(f"   Trace ID: {trace2.id}")

# --- Trace 3: Error trace ---
print("\n3. Logging an error trace (Strands runtime)...")
trace3 = client.trace(
    name="strands_agents/openai/gpt-4.1",
    input={"message": "Search for classified documents"},
    output={"error": "The swarm produced no answer."},
    metadata={
        "framework": "strands_agents",
        "provider": "openai",
        "model": "gpt-4.1",
        "conversation_id": "test-conv-003",
        "run_id": "test-run-003",
        "duration_ms": 5000,
        "total_tokens": 0,
        "error": "The swarm produced no answer.",
    },
    tags=["strands_agents", "openai", "error", "test"],
)
trace3.span(
    name="orchestrator/handoff",
    input={"to": "researcher"},
    output={"summary": "Handed off to researcher"},
    metadata={"agent": "orchestrator"},
)
trace3.span(
    name="researcher/web_search",
    input={"tool": "web_search", "query": "classified documents"},
    output={"output": '{"results": [], "error": "Web search unavailable"}'},
    metadata={"agent": "researcher", "duration_ms": 3000},
)
print(f"   Trace ID: {trace3.id}")

# --- Trace 4: MS Agent Framework GroupChat ---
print("\n4. Logging a GroupChat trace (MS Agent Framework)...")
trace4 = client.trace(
    name="ms_agent_framework/anthropic/claude-sonnet-4-6",
    input={"message": "Plan a trip to Tokyo"},
    output={"answer": "Here's your 5-day Tokyo itinerary..."},
    metadata={
        "framework": "ms_agent_framework",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "conversation_id": "test-conv-004",
        "run_id": "test-run-004",
        "duration_ms": 12000,
        "messages": 5,
    },
    tags=["ms_agent_framework", "anthropic", "test"],
)
for agent_name in ["Researcher", "Retriever", "Analyst", "Compliance Reviewer", "Writer"]:
    trace4.span(
        name=f"{agent_name}/group_chat_turn",
        input={"role": agent_name, "task": "Plan a trip to Tokyo"},
        output={"summary": f"{agent_name} contributed to the plan..."},
        metadata={"agent": agent_name},
    )
print(f"   Trace ID: {trace4.id}")

# Flush all traces
print("\nFlushing traces to Opik...")
client.flush()
time.sleep(2)

print("\n" + "=" * 60)
print("DONE! 4 traces sent to Opik.")
print(f"Open http://localhost:5174 and look for project 'AgentMesh-Test'")
print("=" * 60)
