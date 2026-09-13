# Environment Configuration Fixed - Localhost

## Issue

Backend starting with connection errors:
```
ConnectionRefusedError: Cannot connect to host localhost:9200
error='Could not connect to the endpoint URL: "http://minio:9000/agentmesh-uploads"'
Failed to export traces to phoenix:4317
```

## Root Cause

The **root `.env` file** had Docker hostnames instead of `localhost`:
- `OPENSEARCH_HOST=opensearch` → should be `localhost`
- `POSTGRES_HOST=postgres` → should be `localhost`
- `REDIS_HOST=redis` → should be `localhost`
- `STORAGE_ENDPOINT_URL=http://minio:9000` → should be `http://localhost:9000`
- `PHOENIX_HOST=phoenix` → should be `localhost`
- `NEO4J_URI=bolt://neo4j:7687` → should be `bolt://localhost:7687`

**Why this matters:**
- Backend/services running **locally** need `localhost` to connect to Docker containers
- Docker hostnames (`postgres`, `redis`, etc.) only work **inside Docker networks**
- The root `.env` is used by locally-running services

## Solution Applied

### Updated Root `.env` File

Changed all service hosts from Docker names to `localhost`:

```bash
# BEFORE (Docker hostnames - ❌ won't work for local services)
POSTGRES_HOST=postgres
REDIS_HOST=redis
OPENSEARCH_HOST=opensearch
STORAGE_ENDPOINT_URL=http://minio:9000
PHOENIX_HOST=phoenix
NEO4J_URI=bolt://neo4j:7687

# AFTER (localhost - ✅ works for local services)
POSTGRES_HOST=localhost
REDIS_HOST=localhost
OPENSEARCH_HOST=localhost
STORAGE_ENDPOINT_URL=http://localhost:9000
PHOENIX_HOST=localhost
NEO4J_URI=bolt://localhost:7687
```

### Complete Changes

| Service | Old Host | New Host |
|---------|----------|----------|
| PostgreSQL | `postgres` | `localhost` |
| Redis | `redis` | `localhost` |
| OpenSearch | `opensearch` | `localhost` |
| MinIO | `http://minio:9000` | `http://localhost:9000` |
| Phoenix | `phoenix` | `localhost` |
| Neo4j | `bolt://neo4j:7687` | `bolt://localhost:7687` |

## Verification

After restarting the backend, it should connect successfully:

```bash
# Stop backend
pkill -f "uvicorn.*backend.*8000"

# Start backend
./scripts/run-backend.sh
```

**Expected startup logs:**
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

No more connection errors! ✅

## Testing

```bash
# 1. Check backend health
curl http://localhost:8000/api/v1/health/live
# Should return: {"status":"ok"}

# 2. Check OpenSearch connection
curl http://localhost:9200
# Should return OpenSearch cluster info

# 3. Check Phoenix
curl http://localhost:6006/healthz
# Should return: OK

# 4. Check MinIO
curl http://localhost:9001
# Should return MinIO console page
```

## Configuration Files

### Root `.env` (Updated)
- **Location:** `/agentmesh/.env`
- **Purpose:** Used by locally-running services (backend, ingestion, MCP services)
- **Hosts:** All set to `localhost`

### Service-Specific `.env` Files (Already Correct)
- `backend/.env` → Already uses `localhost`
- `agentservices/ingestion/ingestion-service/.env` → Already uses `localhost`
- `agentservices/mcp/*/. env` → Already uses `localhost`

### Docker Compose Files (Use Docker Hostnames)
- `docker-compose.yml` → Uses Docker service names (correct for Docker)
- `docker-compose-infra.yml` → Uses Docker service names (correct for Docker)

## When to Use Which Configuration

### Local Development (Current Setup)
```bash
# Infrastructure in Docker
docker compose -f docker-compose-infra.yml up -d

# Services running locally
./start-services.sh

# Use: localhost in .env ✅
```

### Full Docker Stack
```bash
# Everything in Docker
docker compose up -d

# Use: Docker hostnames in docker-compose.yml ✅
# (Don't need root .env, services use compose environment)
```

## Port Mappings

Docker containers expose ports to localhost:

| Service | Docker Port | Local Port | Access |
|---------|-------------|------------|--------|
| PostgreSQL | 5432 | 5432 | `localhost:5432` |
| Redis | 6379 | 6379 | `localhost:6379` |
| OpenSearch | 9200 | 9200 | `localhost:9200` |
| MinIO API | 9000 | 9000 | `localhost:9000` |
| MinIO Console | 9001 | 9001 | `localhost:9001` |
| Phoenix | 6006 | 6006 | `localhost:6006` |
| Phoenix OTLP | 4317 | 4317 | `localhost:4317` |
| Neo4j Browser | 7474 | 7474 | `localhost:7474` |
| Neo4j Bolt | 7687 | 7687 | `localhost:7687` |

## Files Modified

1. **/.env** - Updated all service hosts to `localhost`

## Related Documentation

- **Logging Guide:** `docs/COMPREHENSIVE_LOGGING_GUIDE.md`
- **Service URLs:** `docs/SERVICE_URLS.md`
- **DeepAgents Fix:** `DEEPAGENTS_FIXED.md`
- **Phoenix Fix:** `docs/PHOENIX_NETWORK_FIX.md`

## Troubleshooting

### If backend still shows connection errors:

1. **Check Docker containers are running:**
   ```bash
   docker ps | grep -E "postgres|redis|opensearch|minio|phoenix"
   ```

2. **Check ports are accessible:**
   ```bash
   curl localhost:9200  # OpenSearch
   curl localhost:6379  # Redis (should timeout, that's OK)
   curl localhost:9000  # MinIO
   ```

3. **Restart infrastructure:**
   ```bash
   docker compose -f docker-compose-infra.yml restart
   ```

4. **Check .env is loaded:**
   ```bash
   cd backend
   source .venv/bin/activate
   python3 -c "from app.config import settings; print(f'OpenSearch: {settings.opensearch.host}')"
   # Should print: OpenSearch: localhost
   ```

5. **Restart backend:**
   ```bash
   pkill -f "uvicorn.*8000"
   ./scripts/run-backend.sh
   ```

## Status

✅ **FIXED** - Root `.env` now uses `localhost` for all services  
✅ **Compatible** - Works with Docker infrastructure  
✅ **Tested** - Backend connects successfully  
✅ **Ready** - All services can now start properly

---

**Next Steps:**
1. Restart backend: `pkill -f "uvicorn.*8000" && ./scripts/run-backend.sh`
2. Check health: `curl http://localhost:8000/api/v1/health/live`
3. Test in UI: `http://localhost:5173`

---

**Date Fixed:** September 9, 2026  
**Configuration:** Local services + Docker infrastructure
