# AgentMesh Final Project Structure

Complete directory structure after reorganization.

```
agentmesh/
│
├── 📄 README.md                          ← Root README (main documentation)
├── 📄 docker-compose.yml                 ← 17 services orchestration
├── 📄 Makefile                           ← Commands (up, down, migrate, test)
├── 📄 .env                               ← Environment configuration
├── 📄 .gitignore
├── 📄 .dockerignore
│
├── 📁 docs/                              ← All documentation except root README
│   ├── 📄 INDEX.md                       ← Documentation index
│   ├── 📄 architecture.md                ← Architecture deep dive
│   ├── 📄 install.md                     ← Installation guide
│   ├── 📄 PROJECT_STRUCTURE.md           ← Visual project structure
│   ├── 📄 MCP_SERVERS_STRUCTURE.md       ← MCP microservices architecture
│   ├── 📄 MCP_AND_MONGODB_SETUP.md       ← MongoDB + LiteLLM setup
│   ├── 📄 COMPLETE_SETUP_SUMMARY.md      ← Complete features summary
│   └── 📄 FINAL_STRUCTURE.md             ← This file
│
├── 📁 backend/                           ← Main FastAPI application
│   ├── 📄 Dockerfile
│   ├── 📄 requirements.txt               ← 120+ packages
│   ├── 📄 alembic.ini
│   ├── 📁 alembic/                       ← Database migrations
│   │   ├── env.py
│   │   └── versions/
│   └── 📁 app/
│       ├── 📄 __init__.py
│       ├── 📄 main.py                    ← App factory
│       ├── 📄 config.py                  ← Settings (MongoDB, LiteLLM, etc.)
│       ├── 📁 agents/                    ← 7 agent runtimes
│       │   ├── base.py
│       │   ├── definitions.py
│       │   ├── registry.py
│       │   ├── service.py
│       │   ├── frameworks/
│       │   │   ├── adk_runtime.py
│       │   │   ├── adk_workflow_runtime.py
│       │   │   ├── langgraph_runtime.py
│       │   │   ├── deepagents_runtime.py
│       │   │   ├── claude_sdk_runtime.py
│       │   │   ├── ms_agent_runtime.py
│       │   │   └── strands_runtime.py
│       │   └── tools/
│       │       ├── core.py
│       │       └── adapters.py
│       ├── 📁 api/v1/                    ← REST API routes
│       │   ├── chat.py
│       │   ├── files.py
│       │   ├── health.py
│       │   ├── admin_celery.py
│       │   ├── admin_metrics.py
│       │   └── ...
│       ├── 📁 db/                        ← Database layer
│       │   ├── models.py
│       │   ├── repositories.py
│       │   └── session.py
│       ├── 📁 memory/                    ← Memory systems
│       │   ├── short_term.py
│       │   └── long_term.py
│       ├── 📁 search/                    ← Hybrid RAG + vector stores
│       │   ├── client.py                 ← OpenSearch client
│       │   ├── mongo_client.py           ← MongoDB client ⭐ NEW
│       │   ├── hybrid.py                 ← Hybrid search dispatch
│       │   └── indices.py
│       ├── 📁 ingestion/                 ← Document processing
│       │   ├── celery_app.py
│       │   ├── tasks.py
│       │   ├── parsers.py
│       │   └── chunking.py
│       ├── 📁 llm/                       ← LLM abstraction
│       │   └── registry.py
│       ├── 📁 storage/                   ← Object storage
│       │   └── object_store.py
│       ├── 📁 core/                      ← Core utilities
│       │   ├── resilience.py
│       │   ├── resilience_ext.py
│       │   ├── rate_limit.py
│       │   ├── middleware.py
│       │   ├── tracing.py
│       │   ├── logging.py
│       │   └── errors.py
│       └── 📁 schemas/                   ← Pydantic schemas
│
├── 📁 frontend/                          ← React console
│   ├── 📄 Dockerfile
│   ├── 📄 package.json
│   ├── 📄 vite.config.js
│   └── 📁 src/
│       ├── App.jsx
│       ├── hooks/
│       ├── lib/
│       └── components/
│
├── 📁 agentservices/                     ← Independent microservices ⭐ NEW
│   ├── 📄 README.md                      ← Agent services overview
│   │
│   ├── 📁 mcp/                           ← MCP tool servers (3 servers)
│   │   ├── 📄 README.md                  ← MCP servers documentation
│   │   │
│   │   ├── 📁 mcp-documents/             ← Document management (8081)
│   │   │   ├── 📄 Dockerfile
│   │   │   ├── 📄 requirements.txt       ← 10 packages
│   │   │   ├── 📄 README.md
│   │   │   ├── 📄 .env.example
│   │   │   ├── 📄 .gitignore
│   │   │   └── 📁 app/
│   │   │       ├── __init__.py
│   │   │       ├── server.py             ← 4 tools
│   │   │       ├── config.py
│   │   │       └── logging_config.py
│   │   │
│   │   ├── 📁 mcp-search/                ← Web search (8082)
│   │   │   ├── 📄 Dockerfile
│   │   │   ├── 📄 requirements.txt       ← 8 packages
│   │   │   ├── 📄 README.md
│   │   │   ├── 📄 .env.example
│   │   │   ├── 📄 .gitignore
│   │   │   └── 📁 app/
│   │   │       ├── __init__.py
│   │   │       ├── server.py             ← 2 tools
│   │   │       ├── config.py
│   │   │       └── logging_config.py
│   │   │
│   │   └── 📁 mcp-memory/                ← Long-term memory (8083)
│   │       ├── 📄 Dockerfile
│   │       ├── 📄 requirements.txt       ← 12 packages
│   │       ├── 📄 README.md
│   │       ├── 📄 .env.example
│   │       ├── 📄 .gitignore
│   │       └── 📁 app/
│   │           ├── __init__.py
│   │           ├── server.py             ← 4 tools
│   │           ├── config.py
│   │           └── logging_config.py
│   │
│   ├── 📁 ingestion/                     ← Future: specialized processing
│   │   └── 📄 README.md                  ← Planned services
│   │
│   └── 📁 a2aservers/                    ← Future: agent-to-agent
│       └── 📄 README.md                  ← Planned services
│
├── 📁 infra/                             ← Infrastructure configs
│   ├── 📁 postgres/
│   │   └── init.sql
│   ├── 📁 litellm/
│   │   └── config.yaml                   ← 9 models configured ⭐ FIXED
│   ├── 📁 nginx/
│   │   └── default.conf
│   └── 📁 opik/
│
├── 📁 scripts/                           ← Utility scripts
│   ├── seed.sh
│   ├── smoke.sh
│   └── reindex.sh
│
├── 📁 notebook/                          ← Jupyter experiments
│   └── Agentic_RAG.ipynb
│
└── 📁 .git/                              ← Version control
```

## Key Changes from Original Structure

### ✅ Organized Documentation
**Before:** All `.md` files scattered in root  
**After:** All docs in `docs/` except root `README.md`

- `docs/INDEX.md` - Central documentation index
- `docs/architecture.md` - Existing architecture doc
- `docs/install.md` - Installation guide
- `docs/PROJECT_STRUCTURE.md` - Visual structure
- `docs/MCP_SERVERS_STRUCTURE.md` - MCP architecture
- `docs/MCP_AND_MONGODB_SETUP.md` - Setup guides
- `docs/COMPLETE_SETUP_SUMMARY.md` - Feature summary

### ✅ Independent Agent Services
**Before:** MCP servers inside backend as `backend/app/mcp/`  
**After:** Independent microservices in `agentservices/mcp/`

```
agentservices/
├── mcp/              ← 3 independent MCP servers
├── ingestion/        ← Future: processing services
└── a2aservers/       ← Future: agent-to-agent
```

Each service:
- Own Dockerfile
- Own requirements.txt (8-12 packages vs 120+)
- Own README with usage docs
- Own .env.example
- Own .gitignore
- Standalone execution

### ✅ MongoDB Vector Backend
**Added:** `backend/app/search/mongo_client.py`  
**Updated:** `hybrid.py`, `indices.py`, `tasks.py`, `long_term.py`, `health.py`

Config-driven via `VECTOR_BACKEND=opensearch` or `mongodb`

### ✅ LiteLLM Gateway Fixed
**Added:** `infra/litellm/config.yaml` with proper DB integration  
**Fixed:** Missing `DATABASE_URL` and `LITELLM_SALT_KEY`

## File Counts

| Component | Files | Dependencies |
|---|---|---|
| Backend | 50+ Python files | 120+ packages |
| MCP Documents | 4 Python files | 10 packages |
| MCP Search | 4 Python files | 8 packages |
| MCP Memory | 4 Python files | 12 packages |
| Frontend | 30+ JS/JSX files | 20+ packages |
| Documentation | 8 markdown files | - |

## Docker Services (17)

```
Core Application (4)
├── frontend (8080)
├── backend (8000)
├── celery-worker
└── flower (5555)

MCP Servers (3) ⭐ NEW
├── mcp-documents (8081)
├── mcp-search (8082)
└── mcp-memory (8083)

LLM Gateway (1) ⭐ FIXED
└── litellm (4000)

Datastores (7)
├── postgres (5432)
├── redis (6379)
├── opensearch (9200)
├── mongodb (27017) ⭐ NEW
├── neo4j (7474)
├── pinecone (5081-5090)
└── minio (9000, 9001)

Observability (2)
├── phoenix (6006)
└── opik (disabled)
```

## Build Contexts

```yaml
backend:          ./backend
frontend:         ./frontend
mcp-documents:    ./agentservices/mcp/mcp-documents
mcp-search:       ./agentservices/mcp/mcp-search
mcp-memory:       ./agentservices/mcp/mcp-memory
```

## Quick Navigation

### Start Command
```bash
docker compose up -d --build
```

### Key URLs
```
Frontend:     http://localhost:8080
Backend API:  http://localhost:8000/docs
LiteLLM UI:   http://localhost:4000/ui (key: sk-agentmesh-local)
Phoenix:      http://localhost:6006
MCP Docs:     http://localhost:8081/health
MCP Search:   http://localhost:8082/health
MCP Memory:   http://localhost:8083/health
```

### Development
```bash
# Backend
cd backend && python -m uvicorn app.main:app --reload

# MCP server
cd agentservices/mcp/mcp-documents
python -m app.server

# Frontend
cd frontend && npm run dev
```

## Summary

✅ **Documentation organized** - All `.md` files in `docs/` with central index  
✅ **MCP servers independent** - Separate projects in `agentservices/mcp/`  
✅ **MongoDB backend added** - Alternative to OpenSearch  
✅ **LiteLLM gateway fixed** - Database integration complete  
✅ **Future-ready structure** - Room for ingestion and A2A services  

**Total Services:** 17  
**Independent Microservices:** 3 (MCP servers)  
**Vector Backends:** 2 (OpenSearch + MongoDB)  
**Documentation Files:** 8 (all in docs/)
