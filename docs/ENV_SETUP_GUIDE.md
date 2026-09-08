# Environment Variables Setup Guide - Local Development

## Overview

When running AgentMesh locally (infrastructure in Docker, applications on HOST), you need environment variables configured differently than the Docker Compose setup.

**Key Difference:**
- **Docker Compose**: Services use internal hostnames like `postgres`, `redis`, `opensearch`
- **Local Apps**: Must use `localhost` because they run on your HOST machine

---

## Quick Start

### Option 1: Automatic (Recommended)

The `start-local.sh` script automatically creates `.env` files in each service directory:

```bash
./start-local.sh
```

This creates:
- `backend/.env`
- `agentservices/ingestion/ingestion-service/.env`
- `agentservices/mcp/mcp-documents/.env`
- `agentservices/mcp/mcp-search/.env`
- `agentservices/mcp/mcp-memory/.env`

Each file contains all necessary variables with `localhost` for infrastructure services.

### Option 2: Source in Shell

Export variables to your current terminal session:

```bash
source export-env.sh
```

Then run applications normally:

```bash
cd backend
uvicorn app.main:app --reload
```

### Option 3: Manual .env Files

Copy `.env.local` template to each service:

```bash
cp .env.local backend/.env
cp .env.local agentservices/ingestion/ingestion-service/.env
# etc.
```

---

## Environment Variables Explained

### Infrastructure Services (Docker → localhost)

These services run in Docker but apps access them via `localhost`:

| Variable | Docker Value | Local Value | Port |
|----------|-------------|-------------|------|
| `POSTGRES_HOST` | `postgres` | `localhost` | 5432 |
| `REDIS_HOST` | `redis` | `localhost` | 6379 |
| `OPENSEARCH_HOST` | `opensearch` | `localhost` | 9200 |
| `STORAGE_ENDPOINT_URL` | `http://minio:9000` | `http://localhost:9000` | 9000 |
| `MONGODB_URI` | `mongodb://mongodb:27017` | `mongodb://localhost:27017` | 27017 |
| `NEO4J_URI` | `bolt://neo4j:7687` | `bolt://localhost:7687` | 7687 |
| `LITELLM_BASE_URL` | `http://litellm:4000` | `http://localhost:4000` | 4000 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://phoenix:4317` | `http://localhost:4317` | 4317 |

### Application Services (Local)

When running applications locally, they communicate via localhost:

```bash
BACKEND_URL=http://localhost:8000
INGESTION_SERVICE_URL=http://localhost:8001
MCP_DOCUMENTS_URL=http://localhost:8081
MCP_SEARCH_URL=http://localhost:8082
MCP_MEMORY_URL=http://localhost:8083
```

### API Keys

API keys are shared across all services. Add them to root `.env`:

```bash
# .env file (in project root)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
TAVILY_API_KEY=tvly-...
```

The `start-local.sh` script automatically copies these to each service's `.env` file.

---

## Complete Variable Reference

### Core Application

```bash
ENVIRONMENT=local
LOG_LEVEL=DEBUG
LOG_FORMAT=console
```

### PostgreSQL Database

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=agentmesh
POSTGRES_PASSWORD=agentmesh
POSTGRES_DB=agentmesh
```

### OpenSearch (Vector Search)

```bash
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=Agentmesh#2026
OPENSEARCH_USE_SSL=false
OPENSEARCH_EMBEDDING_DIM=1536
```

### Redis (Cache & Queue)

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
```

### MinIO (Object Storage)

```bash
STORAGE_BACKEND=minio
STORAGE_ENDPOINT_URL=http://localhost:9000
STORAGE_ACCESS_KEY=minioadmin
STORAGE_SECRET_KEY=minioadmin
STORAGE_BUCKET=agentmesh-uploads
```

### Agent Configuration

```bash
AGENT_FRAMEWORK=langgraph
AGENT_PROVIDER=anthropic
AGENT_MODEL=claude-sonnet-4-6
AGENT_TEMPERATURE=0.2
AGENT_ENABLE_LONG_TERM_MEMORY=true
```

### Ingestion & Embedding

```bash
INGESTION_EMBEDDING_PROVIDER=openai
INGESTION_EMBEDDING_MODEL=text-embedding-3-small
SEARCH_PROVIDER=auto
```

### LiteLLM Proxy

```bash
LITELLM_ENABLED=true
LITELLM_BASE_URL=http://localhost:4000
LITELLM_MASTER_KEY=sk-agentmesh-local
```

### MongoDB

```bash
VECTOR_BACKEND=opensearch
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=agentmesh
```

### MCP Servers

```bash
MCP_DOCUMENTS_URL=http://localhost:8081
MCP_SEARCH_URL=http://localhost:8082
MCP_MEMORY_URL=http://localhost:8083
```

### Phoenix (AI Observability)

```bash
PHOENIX_ENABLED=true
PHOENIX_HOST=localhost
PHOENIX_GRPC_PORT=4317
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

### Neo4j (Graph Database)

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_AUTH=neo4j/agentmesh
```

### Opik (Optional)

```bash
OPIK_ENABLED=false
OPIK_URL=http://localhost:8080
```

### Service URLs

```bash
BACKEND_URL=http://localhost:8000
INGESTION_SERVICE_URL=http://localhost:8001
```

---

## Usage Patterns

### Pattern 1: Run with Auto-Generated .env

```bash
# 1. Start infrastructure and create .env files
./start-local.sh

# 2. Run backend (uses backend/.env automatically)
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload

# 3. Run ingestion service (uses its .env automatically)
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate
uvicorn app.main:app --port 8001 --reload
```

### Pattern 2: Export to Shell

```bash
# 1. Start infrastructure only
docker compose -f docker-compose-infra.yml up -d

# 2. Export variables
source export-env.sh

# 3. Run backend
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

### Pattern 3: Manual .env Management

```bash
# 1. Create .env in each service directory
cat > backend/.env << 'EOF'
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
# ... rest of variables
EOF

# 2. Run services
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

---

## Troubleshooting

### Issue: "Connection refused" to database/redis/etc

**Cause:** Service trying to connect to docker hostname instead of localhost

**Fix:** Check `.env` file in service directory:
```bash
# Wrong (Docker internal)
POSTGRES_HOST=postgres

# Correct (Local access)
POSTGRES_HOST=localhost
```

### Issue: API keys not found

**Cause:** API keys not in service's `.env` file

**Fix 1:** Add keys to root `.env`, then re-run `./start-local.sh`

**Fix 2:** Manually add to service `.env`:
```bash
echo "OPENAI_API_KEY=sk-..." >> backend/.env
```

### Issue: Environment variables not loading

**Cause:** Wrong sourcing syntax or .env not in correct location

**Fix:**
```bash
# Must use 'source' or '.' to export to current shell
source export-env.sh

# Running as ./export-env.sh won't work (runs in subprocess)
```

### Issue: Different values in different terminals

**Cause:** Each terminal needs separate `source export-env.sh`

**Fix:** Either:
1. Source in each terminal
2. Use .env files (automatically loaded by Python/Node)
3. Add to shell profile (`~/.zshrc` or `~/.bashrc`)

---

## Verification

### Check if variables are set:

```bash
# After sourcing export-env.sh
echo $POSTGRES_HOST    # Should print: localhost
echo $REDIS_HOST       # Should print: localhost
echo $OPENAI_API_KEY   # Should print: sk-...
```

### Check .env files:

```bash
# Check backend .env
cat backend/.env | grep POSTGRES_HOST

# Check ingestion service .env
cat agentservices/ingestion/ingestion-service/.env | grep POSTGRES_HOST
```

### Test connection:

```bash
# Test PostgreSQL
psql -h localhost -p 5432 -U agentmesh -d agentmesh

# Test Redis
redis-cli -h localhost -p 6379 ping

# Test OpenSearch
curl http://localhost:9200

# Test MinIO
curl http://localhost:9000/minio/health/live
```

---

## Automation

### Add to Shell Profile (Optional)

Add to `~/.zshrc` or `~/.bashrc` for automatic loading:

```bash
# In ~/.zshrc
if [ -f ~/path/to/agentmesh/export-env.sh ]; then
    source ~/path/to/agentmesh/export-env.sh
fi
```

### VS Code Tasks (Optional)

Create `.vscode/tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Backend with Env",
      "type": "shell",
      "command": "source export-env.sh && cd backend && source .venv/bin/activate && uvicorn app.main:app --reload",
      "problemMatcher": [],
      "group": "build"
    }
  ]
}
```

---

## Summary

**For most users:**
1. Run `./start-local.sh` once
2. Each service gets its `.env` file automatically
3. Start services normally (`uvicorn`, `npm run dev`, etc.)

**For manual control:**
1. Copy `.env.local` template
2. Customize per service
3. Or use `source export-env.sh` for shell export

**Key point:** Always use `localhost` for infrastructure services when running apps locally!

---

## Related Files

- `.env.local` - Template with all variables
- `export-env.sh` - Shell export script
- `start-local.sh` - Automated startup (creates .env files)
- `docker-compose-infra.yml` - Infrastructure services
- `LOCAL_INSTALL.md` - Complete setup guide
- `QUICK_START.md` - Quick reference

---

**Last Updated:** 2026-09-07
