# MCP Tool Servers

Model Context Protocol (MCP) servers exposing tool capabilities to AI agents.

## Servers

### mcp-documents (Port 8081)
Document management and hybrid search operations.

**Tools:**
- `list_documents` - Paginated document listing
- `get_document_info` - Full document metadata
- `search_documents` - Hybrid RAG search (BM25 + vector)
- `get_document_stats` - Corpus statistics

**Dependencies:** Postgres, OpenSearch  
**Image:** `agentmesh-mcp-documents`

### mcp-search (Port 8082)
Web search and corpus overview operations.

**Tools:**
- `web_search` - Tavily/DuckDuckGo web search
- `get_corpus_overview` - Document corpus summary

**Dependencies:** OpenSearch  
**Image:** `agentmesh-mcp-search`

### mcp-memory (Port 8083)
Long-term memory operations with vector search.

**Tools:**
- `recall_memories` - Semantic memory recall
- `store_memory` - Save new long-term facts
- `forget_memory` - GDPR deletion
- `list_memories` - List all user memories

**Dependencies:** Postgres, OpenSearch/MongoDB  
**Image:** `agentmesh-mcp-memory`

## Architecture

Each MCP server:
- **Independent project** with own Dockerfile, requirements.txt
- **FastMCP framework** with SSE transport
- **Minimal dependencies** (8-12 packages vs 120+ in main backend)
- **Health check** at `/health`
- **Pydantic configuration** from environment variables
- **Structured logging** with structlog

## Running Locally

```bash
# Start a single server
cd mcp-documents
pip install -r requirements.txt
cp .env.example .env
# Edit .env
python -m app.server

# Or use Docker
docker build -t mcp-documents .
docker run -p 8081:8081 --env-file .env mcp-documents
```

## Running All MCP Servers

```bash
# From project root
docker compose up -d mcp-documents mcp-search mcp-memory

# Check health
curl http://localhost:8081/health
curl http://localhost:8082/health
curl http://localhost:8083/health
```

## Integration with Backend

The main backend depends on all 3 MCP servers being healthy:

```yaml
backend:
  depends_on:
    mcp-documents: { condition: service_healthy }
    mcp-search: { condition: service_healthy }
    mcp-memory: { condition: service_healthy }
```

Backend connects via environment variables:
- `MCP_DOCUMENTS_URL=http://mcp-documents:8081`
- `MCP_SEARCH_URL=http://mcp-search:8082`
- `MCP_MEMORY_URL=http://mcp-memory:8083`

## Development

Each server is a **placeholder implementation** with TODO comments. To make functional:

1. Implement database/search queries in each `app/server.py`
2. Add helper modules (e.g., `app/db.py`, `app/search.py`)
3. Test locally before containerizing
4. Update tests and documentation

## Scaling

Scale individual servers based on load:

```bash
docker compose up -d --scale mcp-documents=3
docker compose up -d --scale mcp-search=2
docker compose up -d --scale mcp-memory=3
```

## Adding New MCP Servers

1. Create new directory: `agentservices/mcp/mcp-newserver/`
2. Copy structure from existing server
3. Update `docker-compose.yml` with new service
4. Add to backend dependencies
5. Document in this README
