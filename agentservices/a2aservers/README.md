# Agent-to-Agent (A2A) Servers

Inter-agent communication and orchestration services (future).

## Planned Services

### task-delegator (Port 8101)
Agent task delegation and routing:
- Receives task from orchestrator agent
- Determines best specialist agent for task
- Routes request with context
- Tracks delegation chain
- Returns aggregated results

### result-aggregator (Port 8102)
Multi-agent result fusion:
- Collects results from parallel agents
- Resolves conflicts (consensus, voting, LLM judge)
- Merges complementary results
- Produces unified answer
- Tracks quality metrics

### agent-coordinator (Port 8103)
Agent workflow orchestration:
- Sequential agent chains
- Parallel agent fan-out
- Conditional routing based on intermediate results
- Loop detection and prevention
- Deadlock resolution

### orchestration-hub (Port 8104)
Central coordination for multi-agent systems:
- Agent registry (capabilities, availability, load)
- Load balancing across agent instances
- Circuit breaking for failed agents
- Retry with different agents
- Observability (agent call graphs, latencies)

## Why A2A Servers?

Current system has agents calling tools. Future systems have **agents calling agents**:

1. **Specialization** - Expert agents for narrow domains
2. **Collaboration** - Multiple agents solve complex tasks together
3. **Scalability** - Distribute work across agent pool
4. **Resilience** - Failover to backup agents
5. **Observability** - Track multi-agent workflows

## Use Cases

### Multi-Agent Research
```
User: "Compare pricing models of 5 competitors"

Orchestrator → Task Delegator
             → Researcher Agent 1: Competitor A pricing
             → Researcher Agent 2: Competitor B pricing
             → Researcher Agent 3: Competitor C pricing
             → Researcher Agent 4: Competitor D pricing
             → Researcher Agent 5: Competitor E pricing
             → Result Aggregator → Analyst Agent (comparison)
             → Writer Agent (report)
             → User
```

### Expert Consultation
```
User: "Is this contract clause standard?"

Orchestrator → Legal Expert Agent (contract analysis)
             → Policy Agent (compliance check)
             → Risk Agent (risk assessment)
             → Result Aggregator (consensus)
             → User
```

### Hierarchical Delegation
```
User: "Plan a product launch"

Orchestrator → Planning Agent
             → Market Research Agent → Data Collector Agents
             → Creative Agent → Copywriter Agents
             → Timeline Agent → Project Manager Agent
             → Budget Agent → Finance Analyst Agent
             → Coordinator (merges plans)
             → User
```

## Architecture Pattern

```
agentservices/a2aservers/
├── task-delegator/
│   ├── app/
│   │   ├── server.py          # FastAPI
│   │   ├── router.py          # Agent routing logic
│   │   ├── registry.py        # Agent capabilities registry
│   │   └── tracking.py        # Delegation chain tracking
│   └── Dockerfile
│
├── result-aggregator/
│   ├── app/
│   │   ├── server.py
│   │   ├── fusion.py          # Result fusion strategies
│   │   ├── conflict.py        # Conflict resolution
│   │   └── quality.py         # Quality scoring
│   └── Dockerfile
│
├── agent-coordinator/
│   ├── app/
│   │   ├── server.py
│   │   ├── workflows.py       # Workflow definitions
│   │   ├── executor.py        # Workflow execution
│   │   └── state.py           # State management
│   └── Dockerfile
│
└── orchestration-hub/
    ├── app/
    │   ├── server.py
    │   ├── registry.py        # Agent registry
    │   ├── balancer.py        # Load balancing
    │   ├── breaker.py         # Circuit breakers
    │   └── observability.py   # Tracing, metrics
    └── Dockerfile
```

## API Patterns

### Task Delegation
```bash
POST /delegate
{
  "task": "Analyze quarterly financials",
  "context": {...},
  "required_capabilities": ["financial_analysis", "data_visualization"],
  "timeout_seconds": 300
}

Response:
{
  "delegation_id": "uuid",
  "assigned_agent": "financial-analyst-03",
  "status": "in_progress"
}
```

### Result Aggregation
```bash
POST /aggregate
{
  "results": [
    {"agent": "analyst-1", "result": {...}, "confidence": 0.9},
    {"agent": "analyst-2", "result": {...}, "confidence": 0.85},
    {"agent": "analyst-3", "result": {...}, "confidence": 0.95}
  ],
  "strategy": "consensus"  # or "voting", "llm_judge", "highest_confidence"
}

Response:
{
  "aggregated_result": {...},
  "confidence": 0.92,
  "conflicts_resolved": 2,
  "consensus_level": "high"
}
```

## Implementation Priority

1. **orchestration-hub** - High (foundational for A2A)
2. **task-delegator** - High (needed first)
3. **result-aggregator** - Medium (enables parallel agents)
4. **agent-coordinator** - Low (advanced workflows)

## Integration with AgentMesh

A2A servers sit **between** the main backend and specialist agents:

```
User → Backend → Orchestration Hub → Specialist Agents
                       ↓
                Task Delegator → Agent Pool
                       ↓
                Result Aggregator → Backend → User
```

The 7 current agent runtimes (LangGraph, ADK, etc.) become **orchestration engines** that use A2A servers to delegate to specialist agents.
