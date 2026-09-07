# MCP Memory Server

Standalone MCP server exposing long-term memory operations.

## Tools

- `recall_memories(user_id, query, conversation_id=None, top_k=5)` - Semantic memory recall
- `store_memory(user_id, content, conversation_id=None, importance=5, kind='fact')` - Store new memory
- `forget_memory(user_id, memory_id=None, conversation_id=None)` - GDPR deletion
- `list_memories(user_id, conversation_id=None, limit=20, offset=0)` - List all memories

## Running Locally

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with OpenAI key for embeddings
python -m app.server
```

Server starts on http://localhost:8083

## Docker

```bash
docker build -t mcp-memory .
docker run -p 8083:8083 \
  -e POSTGRES_DSN=postgresql+asyncpg://... \
  -e OPENSEARCH_HOST=opensearch \
  -e OPENAI_API_KEY=... \
  mcp-memory
```

## Vector Backend

Supports both OpenSearch and MongoDB:

```bash
# OpenSearch (default)
VECTOR_BACKEND=opensearch

# MongoDB Atlas Vector Search
VECTOR_BACKEND=mongodb
```

## Implementation Status

**Current:** Placeholder implementation.

**To Complete:**
1. Create `app/memory.py` with hybrid recall (vector + text search)
2. Create `app/embeddings.py` with OpenAI embedding client
3. Implement storage with memory extraction LLM pass
4. Replace placeholder returns with real vector store queries

## Health Check

```bash
curl http://localhost:8083/health
```
