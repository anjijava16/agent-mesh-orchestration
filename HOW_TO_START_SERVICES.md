# How to Start AgentMesh Services

## Problem with `start-services-with-logs.sh`

The script `start-services-with-logs.sh` shows continuous logs in the console, which **blocks** the script from starting subsequent services (MCP services don't start).

This happens because `tee` streams logs to console continuously, preventing the script from moving to the next service.

---

## ✅ RECOMMENDED SOLUTION

Use **two terminals**: one to start services, another to watch logs.

### Terminal 1: Start Services (Background)

```bash
cd /Users/welcome/Desktop/sai_welcome_hanuman/multiagent_project/agentmesh

./start-services.sh
```

This starts all services in the background:
- ✅ Ingestion Service (port 8001)
- ✅ Celery Worker
- ✅ MCP Documents (port 8081)
- ✅ MCP Search (port 8082)
- ✅ MCP Memory (port 8083)

All logs are saved to `logs/` directory.

### Terminal 2: Watch Logs

```bash
cd /Users/welcome/Desktop/sai_welcome_hanuman/multiagent_project/agentmesh

# Watch all logs
./view-logs.sh all -f

# Or watch specific service:
./view-logs.sh ingestion -f
./view-logs.sh celery -f
./view-logs.sh mcp-docs -f
./view-logs.sh mcp-search -f
./view-logs.sh mcp-memory -f
```

---

## Alternative Options

### Option 1: Start Each Service in Separate Terminal

Best for debugging individual services:

```bash
# Terminal 1: Ingestion
./scripts/run-ingestion.sh

# Terminal 2: Celery
./scripts/run-celery.sh

# Terminal 3: MCP Documents
./scripts/run-mcp-documents.sh

# Terminal 4: MCP Search
./scripts/run-mcp-search.sh

# Terminal 5: MCP Memory
./scripts/run-mcp-memory.sh

# Terminal 6: Backend (if needed)
./scripts/run-backend.sh
```

Each terminal shows logs for that service only.

### Option 2: Background + Manual Tail

```bash
# Start all services (background)
./start-services.sh

# Watch newest logs in real-time
tail -f logs/*_$(date +%Y%m%d)*.log

# Or watch specific log
tail -f logs/ingestion_*.log
tail -f logs/celery_*.log
```

### Option 3: Full Docker Mode

Run everything in Docker (no local services):

```bash
docker compose up -d
```

Access:
- Frontend: http://localhost:8080
- Backend: http://localhost:8000
- All other services: same ports

---

## Quick Commands Summary

| Command | Purpose |
|---------|---------|
| `./start-services.sh` | Start all services in background |
| `./view-logs.sh all -f` | Watch all service logs |
| `./view-logs.sh <service> -f` | Watch specific service logs |
| `./check-services.sh` | Check if services are running |
| `./stop-services.sh` | Stop all services |
| `scripts/run-<service>.sh` | Run individual service with logs |

---

## Checking Service Status

```bash
# Check if services are running
./check-services.sh

# Check specific ports
lsof -i :8001  # Ingestion
lsof -i :8081  # MCP Documents
lsof -i :8082  # MCP Search
lsof -i :8083  # MCP Memory

# Health checks
curl http://localhost:8001/health  # Ingestion
curl http://localhost:8081/health  # MCP Documents
curl http://localhost:8082/health  # MCP Search
curl http://localhost:8083/health  # MCP Memory
```

---

## Viewing Saved Logs

Logs are always saved to `logs/` directory, even when running in background:

```bash
# List all log files
ls -lh logs/

# View latest logs
./view-logs.sh -l

# Read specific log file
cat logs/ingestion_20260909.log
cat logs/celery_20260909.log
cat logs/mcp_documents_20260909.log

# Search for errors
grep -i "error" logs/*.log
```

---

## Troubleshooting

### MCP Services Not Starting

If MCP services aren't starting with `start-services.sh`:

1. **Check logs:**
   ```bash
   cat logs/mcp_documents_*.log
   cat logs/mcp_search_*.log
   cat logs/mcp_memory_*.log
   ```

2. **Start individually to see errors:**
   ```bash
   ./scripts/run-mcp-documents.sh
   ```

3. **Check ports aren't in use:**
   ```bash
   lsof -i :8081
   lsof -i :8082
   lsof -i :8083
   ```

### Services Keep Stopping

Check if Docker infrastructure is running:

```bash
docker ps | grep -E "postgres|redis|opensearch|minio"
```

If not:
```bash
docker compose -f docker-compose-infra.yml up -d
```

### Logs Not Appearing

Logs are saved to `logs/` with timestamp in filename:

```bash
# Find today's logs
ls -lt logs/ | head -10

# Watch newest logs
tail -f logs/ingestion_*.log
```

---

## Complete Startup Sequence

```bash
# 1. Start Docker infrastructure
docker compose -f docker-compose-infra.yml up -d
sleep 30  # Wait for services to be ready

# 2. Verify infrastructure
curl http://localhost:9200  # OpenSearch
curl http://localhost:6006/healthz  # Phoenix

# 3. Start AgentMesh services (Terminal 1)
./start-services.sh

# 4. Watch logs (Terminal 2)
./view-logs.sh all -f

# 5. Start backend (Terminal 3 - optional)
./scripts/run-backend.sh

# 6. Start frontend (Terminal 4 - optional)
./scripts/run-frontend.sh
```

---

## Why `start-services-with-logs.sh` Doesn't Work

The script tries to show logs in the console using `tee`, but:

1. First service (Ingestion) starts and shows logs
2. Logs keep streaming to console continuously
3. Script **never reaches** the next service (Celery)
4. MCP services **never start**

**Solution:** Use background mode (`start-services.sh`) + separate log viewer (`view-logs.sh`)

---

## Best Practice

**For Development:**
```bash
# Terminal 1: Start services
./start-services.sh

# Terminal 2: Watch logs
./view-logs.sh all -f
```

**For Production:**
```bash
# Everything in Docker
docker compose up -d

# View Docker logs
docker logs -f agentmesh-backend
docker logs -f agentmesh-ingestion
```

---

## Summary

✅ **Use:** `./start-services.sh` (background) + `./view-logs.sh all -f` (logs)  
❌ **Don't use:** `./start-services-with-logs.sh` (blocks script execution)

**All logs are always saved to `logs/` directory regardless of which method you use!**
