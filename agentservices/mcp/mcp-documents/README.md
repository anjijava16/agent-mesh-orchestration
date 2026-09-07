# MCP Documents Server

Standalone MCP server exposing document management operations.

## Tools

- `list_documents(user_id, limit=20, offset=0)` - List user's documents with pagination
- `get_document_info(user_id, document_id)` - Get detailed document metadata
- `search_documents(user_id, query, document_ids=None, top_k=5)` - Hybrid search across documents
- `get_document_stats(user_id)` - Get corpus statistics

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your database/OpenSearch credentials

# Run server
python -m app.server
```

Server starts on http://localhost:8081

## Docker

```bash
# Build
docker build -t mcp-documents .

# Run
docker run -p 8081:8081 \
  -e POSTGRES_DSN=postgresql+asyncpg://... \
  -e OPENSEARCH_HOST=opensearch \
  mcp-documents
```

## Implementation Status

**Current:** Placeholder implementation returning stub responses.

**To Complete:**
1. Create `app/db.py` with SQLAlchemy models and repository functions
2. Create `app/search.py` with OpenSearch hybrid search logic
3. Replace placeholder returns in `app/server.py` with real queries
4. Add authentication/authorization checks

## Health Check

```bash
curl http://localhost:8081/health
```
