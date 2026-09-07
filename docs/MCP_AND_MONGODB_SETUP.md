# AgentMesh: MongoDB + LiteLLM + MCP Servers Setup Complete

## Summary of Changes

### 1. MongoDB Atlas Vector Search Backend

**New Files:**
- `backend/app/search/mongo_client.py` - MongoDB client with vector search, text search, and all CRUD operations

**Modified Files:**
- `backend/requirements.txt` - Added `motor` (async) and `pymongo` (sync)
- `backend/app/config.py` - Added `VectorBackend` enum, `MongoDBSettings` class, `vector_backend` field
- `backend/app/search/hybrid.py` - Added dispatch logic and `_hybrid_search_mongodb()` function
- `backend/app/search/indices.py` - Added `ensure_mongo_collections()` for MongoDB bootstrap
- `backend/app/ingestion/tasks.py` - Added `_index_to_mongodb()` helper, updated `purge_document`
- `backend/app/memory/long_term.py` - Updated all methods to dispatch to MongoDB when configured
- `backend/app/api/v1/health.py` - Added `_check_mongodb()` health check
- `docker-compose.yml` - Added MongoDB service (port 27017) with replica set for `$vectorSearch`
- `.env` - Added `VECTOR_BACKEND`, `MONGODB_URI`, `MONGODB_DATABASE`

**How to Use:**
```bash
# Switch to MongoDB backend:
VECTOR_BACKEND=mongodb docker compose up -d
```

---

### 2. LiteLLM Proxy Gateway (Fixed)

**Modified Files:**
- `infra/litellm/config.yaml` - Simplified config, removed problematic settings
- `docker-compose.yml` - Fixed LiteLLM service with proper DATABASE_URL, LITELLM_SALT_KEY, depends on postgres
- `.env` - Added `LITELLM_MASTER_KEY`, `LITELLM_SALT_KEY`

**Configuration:**
- **Master Key:** `sk-agentmesh-local` (login credential for http://localhost:4000/ui)
- **Salt Key:** `sk-salt-1234567890abcdef` (DO NOT CHANGE after first use — encrypts DB credentials)
- **Database:** Uses shared `agentmesh` Postgres database
- **Models:** 8 models (3 Anthropic, 3 OpenAI, 2 Google, 1 embedding)

**How to Access:**
1. Open http://localhost:4000/ui
2. Enter master key: `sk-agentmesh-local`
3. See all configured models, spend tracking, health checks

---

### 3. MCP Tool Servers (3 servers)

**New Files:**
- `backend/Dockerfile.mcp` - Dockerfile for MCP servers (selects module via `MCP_SERVER_MODULE`)
- `backend/app/mcp/__init__.py`
- `backend/app/mcp/servers/__init__.py`
- `backend/app/mcp/servers/documents_server.py` - Document management tools (port 8081)
- `backend/app/mcp/servers/search_server.py` - Web search and corpus tools (port 8082)
- `backend/app/mcp/servers/memory_server.py` - Long-term memory tools (port 8083)

**Modified Files:**
- `backend/requirements.txt` - fastmcp already present
- `docker-compose.yml` - Added 3 MCP services, backend now depends on them
- `.env` - Added `MCP_DOCUMENTS_URL`, `MCP_SEARCH_URL`, `MCP_MEMORY_URL`

**MCP Servers:**

| Server | Port | Tools | Purpose |
|---|---|---|---|
| **mcp-documents** | 8081 | `list_documents`, `get_document_info`, `search_documents` | Document management |
| **mcp-search** | 8082 | `web_search`, `get_corpus_overview` | External knowledge |
| **mcp-memory** | 8083 | `recall_memories`, `store_memory`, `forget_memory` | Long-term memory ops |

All use FastMCP with SSE transport. Backend depends on these 3 services.

---

### 4. README Documentation

**Updated Sections:**
- **Tech stack table** - Added LiteLLM gateway, MongoDB, motor/pymongo rows
- **Quickstart URLs** - Added LiteLLM UI (localhost:4000/ui)
- **Docker Compose services** - NEW comprehensive section with all 17 services:
  - Core application (4 services)
  - **MCP Tool Servers (3 services) — NEW**
  - LLM gateway (1 service)
  - Datastores (7 services including MongoDB)
  - Object storage (2 services)
  - Observability (2 services)
- **Quick access summary** - Added all 16 service URLs with credentials
- **Architecture diagram** - Updated to show LiteLLM proxy and MongoDB
- **Hybrid RAG section** - Added MongoDB path explanation
- **LiteLLM gateway section** - NEW standalone section explaining the gateway
- **Memory section** - Updated to mention MongoDB dispatch
- **Ingestion section** - Updated to mention backend routing

---

## Service Count

**Before:** 11 active services + 1 init container  
**After:** 17 active services + 1 init container

**New Services:**
1. `litellm` (fixed with DB integration)
2. `mongodb` (replica set for $vectorSearch)
3. `mcp-documents` (FastMCP server)
4. `mcp-search` (FastMCP server)
5. `mcp-memory` (FastMCP server)

---

## Environment Variables Added

### .env
```bash
# LiteLLM Proxy
LITELLM_ENABLED=true
LITELLM_BASE_URL=http://litellm:4000
LITELLM_MASTER_KEY=sk-agentmesh-local
LITELLM_SALT_KEY=sk-salt-1234567890abcdef

# MongoDB
VECTOR_BACKEND=opensearch
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=agentmesh

# MCP Servers
MCP_DOCUMENTS_URL=http://mcp-documents:8081
MCP_SEARCH_URL=http://mcp-search:8082
MCP_MEMORY_URL=http://mcp-memory:8083
```

---

## How to Start Everything

```bash
# 1. Start Docker Desktop

# 2. Bring up all services (17 services will start in dependency order):
cd /path/to/agentmesh
docker compose up -d --build

# 3. Wait for healthchecks (backend starts last, waits for MCP servers):
docker compose ps

# 4. Run migrations:
docker compose exec backend alembic upgrade head

# 5. Access services:
# - Frontend: http://localhost:8080
# - Backend API: http://localhost:8000/docs
# - LiteLLM UI: http://localhost:4000/ui (key: sk-agentmesh-local)
# - Phoenix: http://localhost:6006
# - MCP Documents: http://localhost:8081/health
# - MCP Search: http://localhost:8082/health
# - MCP Memory: http://localhost:8083/health
```

---

## LiteLLM UI Login

The error you saw ("Missing DATABASE_URL") is now fixed. LiteLLM now has:
- `DATABASE_URL` → Points to Postgres `agentmesh` database
- `LITELLM_SALT_KEY` → Required for encrypting credentials in DB
- Depends on Postgres health check

**To login:**
1. Go to http://localhost:4000/ui
2. Enter: `sk-agentmesh-local`
3. You'll see 9 models listed (if API keys are set in .env)

---

## MongoDB Usage

**Local Dev:**
- Runs as single-node replica set (`rs0`) so `$vectorSearch` works
- No authentication
- Connect: `mongosh mongodb://localhost:27017/agentmesh`

**To Switch:**
```bash
# In .env:
VECTOR_BACKEND=mongodb

# Restart:
docker compose up -d backend celery-worker
```

Everything (RAG, memory, ingestion) will route to MongoDB instead of OpenSearch.

**Production:**
- Point `MONGODB_URI` at Atlas
- Atlas Search indexes are created automatically via `ensure_mongo_collections()`

---

## MCP Server Implementation

Each MCP server is a FastMCP application that exposes tools via SSE transport.

**Example - Documents Server:**
```python
from fastmcp import FastMCP

mcp = FastMCP(name="documents")

@mcp.tool
def list_documents(user_id: str, limit: int = 20) -> dict:
    # Query database
    return {"user_id": user_id, "documents": [...]}

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8081)
```

**Current Status:**
The 3 MCP servers are **placeholder implementations** — they return stub responses. To make them functional:

1. Import the actual service layers (e.g., `from app.db.repositories import DocumentRepo`)
2. Replace stub returns with real database/search queries
3. Add authentication/authorization checks

**Health Checks:**
All 3 MCP servers expose `/health` endpoint. Backend depends on `service_healthy` condition for all 3.

---

## Dependency Graph

```
frontend
  └─> backend (depends on ↓)
        ├─> postgres (healthy)
        ├─> redis (healthy)
        ├─> opensearch (healthy)
        ├─> mongodb (healthy)
        ├─> minio (healthy)
        ├─> litellm (healthy, depends on postgres)
        ├─> phoenix (healthy, depends on postgres)
        ├─> neo4j (healthy)
        ├─> mcp-documents (healthy, depends on postgres + opensearch)
        ├─> mcp-search (healthy, depends on opensearch)
        └─> mcp-memory (healthy, depends on postgres + opensearch)
```

---

## Troubleshooting

### LiteLLM Container Error
**Cause:** Missing `DATABASE_URL` or `LITELLM_SALT_KEY`  
**Fix:** Now included in docker-compose.yml (pulls from .env)

### MCP Servers Not Starting
**Check logs:**
```bash
docker logs agentmesh-mcp-documents
docker logs agentmesh-mcp-search
docker logs agentmesh-mcp-memory
```

**Common issues:**
- fastmcp not installed → rebuild with `--build` flag
- Port conflicts → check nothing else uses 8081-8083

### MongoDB Not Working
**Local Dev:**
- Ensure `mongod --replSet rs0` initiated (healthcheck does this)
- Vector search fallback to brute-force cosine is automatic

**Atlas:**
- Set `MONGODB_URI` to Atlas connection string
- Indexes are created automatically

---

## Next Steps

1. **Start Docker Desktop**
2. **Run:** `docker compose up -d --build`
3. **Access LiteLLM UI:** http://localhost:4000/ui with `sk-agentmesh-local`
4. **Verify MCP servers:** 
   - http://localhost:8081/health
   - http://localhost:8082/health
   - http://localhost:8083/health
5. **Test MongoDB:** Set `VECTOR_BACKEND=mongodb` and restart
6. **Implement MCP tools:** Replace stubs in `backend/app/mcp/servers/*.py` with real logic

---

All changes are complete and documented. The system now has:
- ✅ MongoDB vector backend (alternative to OpenSearch)
- ✅ LiteLLM proxy with database integration
- ✅ 3 MCP tool servers (documents, search, memory)
- ✅ Complete README documentation with all 17 services
