# AgentMesh Project Structure

```
agentmesh/
├── 📄 README.md                          # Complete documentation (17 services)
├── 📄 docker-compose.yml                 # All services orchestration
├── 📄 Makefile                           # Commands (up, down, migrate, test)
├── 📄 .env                               # Environment configuration
├── 📄 .gitignore
│
├── 📄 MCP_AND_MONGODB_SETUP.md          # MongoDB + LiteLLM setup guide
├── 📄 MCP_SERVERS_STRUCTURE.md          # MCP microservices architecture
├── 📄 COMPLETE_SETUP_SUMMARY.md         # This summary
├── 📄 PROJECT_STRUCTURE.md              # Visual structure (this file)
│
├── 📁 backend/                           # FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt                  # 120+ packages
│   ├── alembic.ini
│   ├── alembic/                         # Database migrations
│   └── app/
│       ├── main.py                      # App factory
│       ├── config.py                    # Settings + MongoDB + LiteLLM
│       ├── agents/                      # 7 agent runtimes
│       ├── api/v1/                      # REST API routes
│       ├── db/                          # SQLAlchemy models + repos
│       ├── memory/                      # Short-term + long-term
│       ├── search/                      # Hybrid RAG + mongo_client.py
│       ├── ingestion/                   # Celery tasks
│       ├── llm/                         # Model registry
│       └── ...
│
├── 📁 frontend/                          # React + Vite console
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│
├── 📁 infra/                             # Config files
│   ├── postgres/init.sql
│   ├── litellm/config.yaml              # 9 models configured
│   ├── nginx/
│   └── ...
│
├── 🚀 mcp-documents/                     # Independent MCP server
│   ├── Dockerfile                        # Own image
│   ├── requirements.txt                  # 10 packages
│   ├── README.md                         # Tools + usage
│   ├── .env.example
│   ├── .gitignore
│   └── app/
│       ├── __init__.py
│       ├── server.py                     # 4 tools (list, info, search, stats)
│       ├── config.py                     # Pydantic settings
│       └── logging_config.py
│
├── 🚀 mcp-search/                        # Independent MCP server
│   ├── Dockerfile                        # Own image
│   ├── requirements.txt                  # 8 packages
│   ├── README.md                         # Tools + usage
│   ├── .env.example
│   ├── .gitignore
│   └── app/
│       ├── __init__.py
│       ├── server.py                     # 2 tools (web_search, corpus_overview)
│       ├── config.py
│       └── logging_config.py
│
├── 🚀 mcp-memory/                        # Independent MCP server
│   ├── Dockerfile                        # Own image
│   ├── requirements.txt                  # 12 packages
│   ├── README.md                         # Tools + usage
│   ├── .env.example
│   ├── .gitignore
│   └── app/
│       ├── __init__.py
│       ├── server.py                     # 4 tools (recall, store, forget, list)
│       ├── config.py                     # Vector backend dispatch
│       └── logging_config.py
│
├── 📁 notebook/                          # Jupyter experiments
├── 📁 scripts/                           # Seed, smoke test
└── 📁 docs/                              # Architecture docs
```

## Docker Services

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (8080)                             │
│                      React + Vite + nginx                           │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                        Backend (8000)                               │
│                  FastAPI + 7 Agent Runtimes                         │
│  depends on: postgres, redis, opensearch, mongodb, minio,          │
│              litellm, phoenix, neo4j, 3 MCP servers                 │
└───┬───────┬───────┬───────┬───────┬───────┬───────┬────────────────┘
    │       │       │       │       │       │       │
    │   ┌───▼───┐ ┌─▼─────┐│   ┌───▼────┐ │   ┌───▼────────┐
    │   │LiteLLM│ │Phoenix││   │MongoDB │ │   │ MCP Docs   │
    │   │ 4000  │ │ 6006  ││   │ 27017  │ │   │   8081     │
    │   │       │ │       ││   │        │ │   │            │
    │   │ proxy │ │ OTLP  ││   │replica │ │   │ list_docs  │
    │   │models │ │traces ││   │  set   │ │   │ get_info   │
    │   │spend  │ │       ││   │$vector │ │   │ search     │
    │   └───┬───┘ └───┬───┘│   │Search  │ │   │ stats      │
    │       │         │    │   └────────┘ │   └────────────┘
    │   ┌───▼─────────▼────▼──────────┐   │   ┌────────────┐
    │   │      Postgres (5432)        │   │   │ MCP Search │
    │   │  agentmesh + phoenix DBs    │   │   │   8082     │
    │   │  LiteLLM spend tracking     │   │   │            │
    │   └─────────────────────────────┘   │   │ web_search │
    │                                     │   │ corpus_ovw │
    │   ┌────────────────────────────┐    │   └────────────┘
    │   │    OpenSearch (9200)       │    │   ┌────────────┐
    │   │  docs + memory indices     │    │   │ MCP Memory │
    │   │  BM25 + kNN hybrid         │    │   │   8083     │
    │   └────────────────────────────┘    │   │            │
    │                                     │   │recall_mem  │
    │   ┌──────┐ ┌──────┐ ┌──────┐      │   │store_mem   │
    └───►Redis │ │MinIO │ │Neo4j │      │   │forget_mem  │
        │ 6379 │ │ 9000 │ │ 7474 │      │   │list_mem    │
        │Celery│ │  S3  │ │Graph │      │   └────────────┘
        └──────┘ └──────┘ └──────┘      │
                                         │
         Celery Worker                   │
         (document ingestion)            │
         depends on: redis, postgres,    │
                     opensearch, minio   │
                                         └───────────────────────────────┘
```

## Service Dependencies

```
postgres          # No deps
redis             # No deps
opensearch        # No deps
mongodb           # No deps
minio             # No deps
neo4j             # No deps
pinecone          # No deps

litellm           # → postgres
phoenix           # → postgres

mcp-documents     # → postgres, opensearch
mcp-search        # → opensearch
mcp-memory        # → postgres, opensearch

backend           # → ALL above (postgres, redis, opensearch, mongodb, minio,
                  #    litellm, phoenix, neo4j, 3 MCP servers)
                  
celery-worker     # → postgres, redis, opensearch, minio

frontend          # → backend
```

## Key Differentiators

### 1. MongoDB as Vector Backend
- Config-driven: `VECTOR_BACKEND=opensearch` or `mongodb`
- Same interface, different implementation
- Local: single-node replica set
- Production: Atlas with `$vectorSearch`

### 2. LiteLLM Gateway
- Single egress for all LLM traffic
- 9 models (Anthropic, OpenAI, Google)
- Latency-based routing
- Spend tracking in Postgres
- UI: http://localhost:4000/ui (key: sk-agentmesh-local)

### 3. Independent MCP Servers ⭐
- **3 separate microservices** (not embedded in backend)
- Own Dockerfile, requirements.txt, config, README
- 8-12 dependencies each (vs 120+ in backend)
- Can be developed, versioned, scaled, deployed independently
- FastMCP with SSE transport
- Backend depends on all 3 being healthy

## File Counts

```
Backend:          120+ dependencies, 50+ Python files
MCP Documents:     10 dependencies,  4 Python files
MCP Search:         8 dependencies,  4 Python files
MCP Memory:        12 dependencies,  4 Python files
```

## URLs Quick Reference

```
http://localhost:8080     Frontend (React console)
http://localhost:8000     Backend API (/docs for OpenAPI)
http://localhost:4000     LiteLLM Proxy (/ui, key: sk-agentmesh-local)
http://localhost:6006     Phoenix (AI observability)
http://localhost:8081     MCP Documents (/health)
http://localhost:8082     MCP Search (/health)
http://localhost:8083     MCP Memory (/health)
http://localhost:9001     MinIO Console (minioadmin / minioadmin)
http://localhost:7474     Neo4j Browser (neo4j / agentmesh2026)
http://localhost:5601     OpenSearch Dashboards (make tools)
http://localhost:5555     Flower - Celery UI (make tools)
```

## Start Command

```bash
docker compose up -d --build
```

This builds and starts all 17 services in dependency order:
1. Base datastores (postgres, redis, opensearch, mongodb, minio, neo4j)
2. LiteLLM proxy (waits for postgres)
3. Phoenix (waits for postgres)
4. 3 MCP servers (wait for datastores)
5. Backend (waits for EVERYTHING including MCP servers)
6. Celery worker (waits for datastores)
7. Frontend (waits for backend)

## Implementation Notes

✅ **Complete:**
- Project structure
- Dockerfiles
- Configuration
- Service orchestration
- Health checks
- Documentation

🔨 **To Complete:**
- MCP server implementations (currently return placeholders)
- Add real database queries, vector searches, web search calls
- See TODO comments in each `app/server.py`

---

**Architecture:** Microservices  
**Total Services:** 17  
**MCP Servers:** 3 independent projects  
**Vector Backends:** 2 (OpenSearch + MongoDB)  
**Agent Runtimes:** 7 (LangGraph, ADK pipeline, ADK workflow, DeepAgents, Claude SDK, MS Agent, Strands)
