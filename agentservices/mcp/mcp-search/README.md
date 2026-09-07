# MCP Search Server

Standalone MCP server exposing web search and corpus overview operations.

## Tools

- `web_search(query, max_results=5)` - Search the web via Tavily or DuckDuckGo
- `get_corpus_overview(user_id)` - Get document corpus statistics

## Running Locally

```bash
pip install -r requirements.txt
cp .env.example .env
python -m app.server
```

Server starts on http://localhost:8082

## Docker

```bash
docker build -t mcp-search .
docker run -p 8082:8082 -e TAVILY_API_KEY=... mcp-search
```

## Implementation Status

**Current:** Placeholder implementation.

**To Complete:**
1. Create `app/web_search.py` with Tavily + DuckDuckGo integration
2. Create `app/corpus.py` with OpenSearch/database aggregation queries
3. Replace placeholder returns with real API calls

## Health Check

```bash
curl http://localhost:8082/health
```
