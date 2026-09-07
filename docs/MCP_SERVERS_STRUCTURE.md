# MCP Servers - Independent Microservices

All 3 MCP servers are now **independent projects** outside the backend, following microservices architecture.

## Project Structure

```
agentmesh/
├── backend/                  # Main FastAPI application
├── frontend/                 # React UI
├── mcp-documents/            # ← Independent MCP server
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── README.md
│   ├── .env.example
│   └── app/
│       ├── __init__.py
│       ├── server.py
│       ├── config.py
│       └── logging_config.py
├── mcp-search/               # ← Independent MCP server
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── README.md
│   ├── .env.example
│   └── app/
│       ├── __init__.py
│       ├── server.py
│       ├── config.py
│       └── logging_config.py
└── mcp-memory/               # ← Independent MCP server
    ├── Dockerfile
    ├── requirements.txt
    ├── README.md
    ├── .env.example
    └── app/
        ├── __init__.py
        ├── server.py
        ├── config.py
        └── logging_config.py
```

## Each MCP Server Has

1. **Own Dockerfile** - No dependency on backend image
2. **Own requirements.txt** - Minimal dependencies (fastmcp, structlog, db drivers)
3. **Own configuration** - Pydantic settings from env vars
4. **Own README** - Usage instructions, tools list, implementation status
5. **Standalone execution** - Can run independently: `python -m app.server`

## Comparison with Backend-Embedded Approach

### ❌ Before (Embedded in Backend)
```
backend/
├── Dockerfile.mcp          # Reused backend Dockerfile
├── app/
│   └── mcp/
│       └── servers/
│           ├── documents_server.py
│           ├── search_server.py
│           └── memory_server.py
```

**Problems:**
- Shared dependencies with backend (100+ packages)
- Coupled to backend codebase
- Same Docker image for all 3 servers
- Can't scale or version independently

### ✅ After (Independent Microservices)
```
mcp-documents/  # Own project, own Dockerfile, 10 dependencies
mcp-search/     # Own project, own Dockerfile, 8 dependencies
mcp-memory/     # Own project, own Dockerfile, 12 dependencies
```

**Benefits:**
- Minimal dependencies (only what each server needs)
- Independent deployment, scaling, versioning
- Can be developed/tested in isolation
- Follow microservices best practices

## Running Locally (Development)

Each server can run standalone:

```bash
# MCP Documents Server
cd mcp-documents
pip install -r requirements.txt
cp .env.example .env
# Edit .env with database credentials
python -m app.server
# → http://localhost:8081

# MCP Search Server
cd mcp-search
pip install -r requirements.txt
cp .env.example .env
python -m app.server
# → http://localhost:8082

# MCP Memory Server
cd mcp-memory
pip install -r requirements.txt
cp .env.example .env
# Edit .env with OpenAI key for embeddings
python -m app.server
# → http://localhost:8083
```

## Running with Docker Compose

All 3 servers build from their own directories:

```bash
cd agentmesh/
docker compose build mcp-documents mcp-search mcp-memory
docker compose up -d mcp-documents mcp-search mcp-memory
```

**Build contexts:**
- `mcp-documents`: `./mcp-documents`
- `mcp-search`: `./mcp-search`
- `mcp-memory`: `./mcp-memory`

The backend depends on all 3 being healthy.

## Dependencies

### MCP Documents (10 packages)
```txt
fastmcp, mcp, pydantic, pydantic-settings
asyncpg, psycopg2-binary, SQLAlchemy[asyncio]
opensearch-py[async]
structlog
httpx, python-dotenv
```

### MCP Search (8 packages)
```txt
fastmcp, mcp, pydantic, pydantic-settings
ddgs, httpx
opensearch-py[async], asyncpg
structlog, python-dotenv
```

### MCP Memory (12 packages)
```txt
fastmcp, mcp, pydantic, pydantic-settings
asyncpg, opensearch-py[async]
motor, pymongo
openai, langchain-openai
structlog, httpx, python-dotenv
```

Compare to backend: **120+ packages** (AI frameworks, LangGraph, ADK, Anthropic SDK, etc.)

## Tools Exposed

### MCP Documents (8081)
- `list_documents(user_id, limit, offset)` - Paginated document list
- `get_document_info(user_id, document_id)` - Full metadata
- `search_documents(user_id, query, document_ids, top_k)` - Hybrid search
- `get_document_stats(user_id)` - Corpus statistics

### MCP Search (8082)
- `web_search(query, max_results)` - Tavily/DuckDuckGo web search
- `get_corpus_overview(user_id)` - Document corpus summary

### MCP Memory (8083)
- `recall_memories(user_id, query, conversation_id, top_k)` - Semantic recall
- `store_memory(user_id, content, conversation_id, importance, kind)` - Store new memory
- `forget_memory(user_id, memory_id, conversation_id)` - GDPR deletion
- `list_memories(user_id, conversation_id, limit, offset)` - List all memories

## Implementation Status

**All 3 servers:** Placeholder implementations with TODO comments.

**To make them functional:**

1. **mcp-documents**:
   - Create `app/db.py` with SQLAlchemy repository functions
   - Create `app/search.py` with OpenSearch hybrid search
   - Replace stubs in `app/server.py`

2. **mcp-search**:
   - Create `app/web_search.py` with Tavily + DuckDuckGo
   - Create `app/corpus.py` with OpenSearch aggregations
   - Replace stubs in `app/server.py`

3. **mcp-memory**:
   - Create `app/memory.py` with hybrid recall (vector + text)
   - Create `app/embeddings.py` with OpenAI embedding client
   - Add LLM extraction pass for `store_memory`
   - Replace stubs in `app/server.py`

## Docker Compose Integration

```yaml
mcp-documents:
  build:
    context: ./mcp-documents  # ← Own directory
    dockerfile: Dockerfile
  environment:
    POSTGRES_DSN: postgresql+asyncpg://...
    OPENSEARCH_HOST: opensearch
  ports: ["8081:8081"]
  depends_on:
    postgres: { condition: service_healthy }
    opensearch: { condition: service_healthy }

# Similar for mcp-search and mcp-memory

backend:
  depends_on:
    mcp-documents: { condition: service_healthy }
    mcp-search: { condition: service_healthy }
    mcp-memory: { condition: service_healthy }
```

Backend waits for all 3 MCP servers to be healthy before starting.

## Health Checks

Each server exposes `/health`:

```bash
curl http://localhost:8081/health  # documents
curl http://localhost:8082/health  # search
curl http://localhost:8083/health  # memory
```

## Deployment Independence

Each server can be:
- **Scaled independently**: `docker compose up -d --scale mcp-documents=3`
- **Versioned independently**: `mcp-documents:1.2.0`, `mcp-search:1.0.5`
- **Deployed separately**: Different repos, different teams
- **Language-agnostic**: Could rewrite one in Go/Rust without touching others

## Next Steps

1. **Start Docker and build all services:**
   ```bash
   docker compose up -d --build
   ```

2. **Verify MCP servers are running:**
   ```bash
   docker ps | grep mcp
   curl http://localhost:8081/health
   curl http://localhost:8082/health
   curl http://localhost:8083/health
   ```

3. **Implement real logic** (currently placeholders):
   - Add database queries to mcp-documents
   - Add web search to mcp-search
   - Add vector search to mcp-memory

4. **Test with backend:**
   - Backend connects to MCP servers via `MCP_DOCUMENTS_URL`, `MCP_SEARCH_URL`, `MCP_MEMORY_URL`
   - Tools are exposed through the agent framework

---

All MCP servers are now **independent microservices** following the same pattern as `account_check_agentic_orchestrator-develop`.
