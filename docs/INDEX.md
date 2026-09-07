# AgentMesh Documentation Index

Complete documentation for the AgentMesh multi-agent orchestration platform.

## Getting Started

- **[../README.md](../README.md)** - Main project README with quickstart and architecture overview
- **[install.md](install.md)** - Detailed installation instructions

## Architecture & Design

- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** - Complete project structure with visual diagrams
- **[architecture.md](architecture.md)** - Architecture deep dive (existing)

## Setup Guides

- **[COMPLETE_SETUP_SUMMARY.md](COMPLETE_SETUP_SUMMARY.md)** - Complete summary of all features and services
- **[MCP_AND_MONGODB_SETUP.md](MCP_AND_MONGODB_SETUP.md)** - MongoDB vector backend + LiteLLM proxy setup
- **[MCP_SERVERS_STRUCTURE.md](MCP_SERVERS_STRUCTURE.md)** - MCP microservices architecture and implementation

## Quick Reference

### All Services (17 Total)

**Core Application (4)**
- frontend (8080)
- backend (8000)
- celery-worker
- flower (5555)

**MCP Servers (3)**
- mcp-documents (8081) - [agentservices/mcp/mcp-documents](../agentservices/mcp/mcp-documents/)
- mcp-search (8082) - [agentservices/mcp/mcp-search](../agentservices/mcp/mcp-search/)
- mcp-memory (8083) - [agentservices/mcp/mcp-memory](../agentservices/mcp/mcp-memory/)

**LLM Gateway (1)**
- litellm (4000)

**Datastores (7)**
- postgres (5432)
- redis (6379)
- opensearch (9200)
- mongodb (27017)
- neo4j (7474)
- pinecone (5081-5090)
- minio (9000, 9001)

**Observability (2)**
- phoenix (6006, 4317)
- opik (disabled)

### Key URLs

```
http://localhost:8080    Frontend Console
http://localhost:8000    Backend API (/docs)
http://localhost:4000    LiteLLM Proxy (/ui, key: sk-agentmesh-local)
http://localhost:6006    Phoenix (AI traces)
http://localhost:8081    MCP Documents (/health)
http://localhost:8082    MCP Search (/health)
http://localhost:8083    MCP Memory (/health)
```

### Environment Variables

Key variables in `.env`:

```bash
# LLM Providers
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=

# LiteLLM Gateway
LITELLM_ENABLED=true
LITELLM_MASTER_KEY=sk-agentmesh-local
LITELLM_SALT_KEY=sk-salt-1234567890abcdef

# Vector Backend
VECTOR_BACKEND=opensearch  # or mongodb
MONGODB_URI=mongodb://mongodb:27017

# MCP Servers
MCP_DOCUMENTS_URL=http://mcp-documents:8081
MCP_SEARCH_URL=http://mcp-search:8082
MCP_MEMORY_URL=http://mcp-memory:8083
```

## Component Documentation

### Agent Services
- **[../agentservices/README.md](../agentservices/README.md)** - Agent services overview
- **[../agentservices/mcp/README.md](../agentservices/mcp/README.md)** - MCP servers documentation
- **[../agentservices/ingestion/README.md](../agentservices/ingestion/README.md)** - Future ingestion services
- **[../agentservices/a2aservers/README.md](../agentservices/a2aservers/README.md)** - Future agent-to-agent servers

### Individual Services
- **[../agentservices/mcp/mcp-documents/README.md](../agentservices/mcp/mcp-documents/README.md)** - Document management MCP server
- **[../agentservices/mcp/mcp-search/README.md](../agentservices/mcp/mcp-search/README.md)** - Search MCP server
- **[../agentservices/mcp/mcp-memory/README.md](../agentservices/mcp/mcp-memory/README.md)** - Memory MCP server

## Topics

### Vector Backends
- OpenSearch (default) - BM25 + kNN with HNSW
- MongoDB Atlas Vector Search - `$vectorSearch` aggregation
- Config via `VECTOR_BACKEND` environment variable
- Both use same RRF fusion and reranking

### LLM Gateway
- LiteLLM proxy at port 4000
- Unified routing to OpenAI, Anthropic, Google
- Latency-based routing
- Spend tracking in Postgres
- UI login: `sk-agentmesh-local`

### Agent Runtimes (7)
1. LangGraph - Explicit supervisor graph
2. Google ADK Pipeline - Declarative orchestration
3. Google ADK Workflow - Graph with HITL gates
4. LangChain DeepAgents - Planning-first
5. Claude Agent SDK - Anthropic harness
6. Microsoft Agent Framework - GroupChat
7. AWS Strands Agents - Swarm with handoffs

### Memory System
- **Short-term:** Postgres (conversation history + rolling summary)
- **Long-term:** OpenSearch or MongoDB (semantic facts)
- Both support GDPR deletion

### Resilience
- Custom async circuit breakers
- tenacity + pybreaker (industry standard)
- Per-tool timeouts and retries
- Graceful degradation

### Observability
- **Arize Phoenix** - Primary (OTLP traces)
- **Opik** - Alternative (disabled by default)
- **structlog** - Structured JSON logs
- **Prometheus** - Metrics endpoint

## Development

### Running Locally
```bash
docker compose up -d --build
docker compose ps
curl http://localhost:8000/api/v1/health
```

### Running Individual Services
```bash
# MCP Document Server
cd agentservices/mcp/mcp-documents
pip install -r requirements.txt
python -m app.server

# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Testing
```bash
make test          # Run all tests
make smoke         # Smoke test (health checks + chat turn)
make seed          # Upload sample document
```

## Troubleshooting

### LiteLLM Not Starting
- Check `DATABASE_URL` is set
- Verify `LITELLM_SALT_KEY` is set
- Check Postgres is healthy

### MCP Servers Not Starting
- Verify Postgres and OpenSearch are healthy
- Check port conflicts (8081-8083)
- Review logs: `docker logs agentmesh-mcp-documents`

### MongoDB Vector Search
- Local: Uses brute-force cosine fallback (no Atlas)
- Production: Point `MONGODB_URI` to Atlas cluster
- Indexes created automatically

## Contributing

See the main README for contribution guidelines.

## License

See the main README for license information.
