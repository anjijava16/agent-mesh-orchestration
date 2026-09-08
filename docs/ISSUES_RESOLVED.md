# Issues Resolved - AgentMesh Services

## Summary of Issues Fixed

This document summarizes all the issues that were identified and resolved for running AgentMesh services locally.

---

## ✅ Issue 1: Ingestion Service `/docs` Endpoint Not Accessible

### Problem
The ingestion service was running on port 8001, but the `/docs` endpoint (Swagger UI) was not accessible.

### Root Cause
FastAPI app initialization did not explicitly configure the docs URLs.

### Solution
Updated `agentservices/ingestion/ingestion-service/app/main.py`:

```python
app = FastAPI(
    title="Ingestion Service",
    description="Microservice for file ingestion and document processing",
    version="1.0.0",
    docs_url="/docs",          # Added
    redoc_url="/redoc",        # Added
    openapi_url="/openapi.json" # Added
)
```

### Verification
```bash
curl http://localhost:8001/docs
# Returns HTML for Swagger UI
```

**Status: ✅ FIXED**

---

## ✅ Issue 2: Phoenix Database Error

### Problem
Phoenix service was crashing with error:
```
asyncpg.exceptions.InvalidCatalogNameError: database "phoenix" does not exist
```

### Root Cause
The PostgreSQL `init.sql` script creates the `phoenix` database, but it only runs on first boot with an empty data volume. If the Docker volume already existed without the phoenix database, it wouldn't be created.

### Solution
1. Manually created the database:
```bash
docker exec agentmesh-postgres psql -U agentmesh -d agentmesh -c "CREATE DATABASE phoenix;"
```

2. Updated `start-services.sh` to automatically check and create the database if missing.

3. Restarted Phoenix:
```bash
docker restart agentmesh-phoenix
```

### Verification
```bash
docker logs agentmesh-phoenix --tail 20
# Shows: "🚀 Phoenix is up and running — open http://localhost:6006"
```

**Status: ✅ FIXED**

---

## ✅ Issue 3: Celery Worker Not Starting

### Problem
Celery worker couldn't connect to Redis when running locally, showing error:
```
Error 8 connecting to redis:6379. nodename nor servname provided, or not known.
```

### Root Cause
Celery was using `REDIS_HOST=redis` (Docker service name) instead of `localhost` for local development.

### Solution
Updated `start-services.sh` to export local environment variables before starting Celery:

```bash
export REDIS_HOST=localhost
export POSTGRES_HOST=localhost
export OPENSEARCH_HOST=localhost

celery -A app.worker.celery_app worker ...
```

### Verification
```bash
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate
celery -A app.worker.celery_app inspect ping
# Returns: pong from celery@hostname
```

**Status: ✅ FIXED**

---

## ✅ Issue 4: MCP Services Not Starting

### Problem
No clear instructions or scripts existed for starting the three MCP services (documents, search, memory) from the root directory.

### Root Cause
Services were nested in subdirectories with their own virtual environments and requirements.

### Solution
Created comprehensive startup script (`start-services.sh`) that:
1. Creates virtual environments for each service
2. Installs dependencies
3. Starts services on correct ports (8081, 8082, 8083)
4. Sets correct environment variables
5. Logs to timestamped log files

### Verification
```bash
./start-services.sh
# Check services
lsof -i :8081 # MCP Documents
lsof -i :8082 # MCP Search
lsof -i :8083 # MCP Memory
```

**Status: ✅ FIXED**

---

## 📝 New Scripts Created

### 1. `start-services.sh`
Comprehensive startup script that:
- Checks and creates Phoenix database
- Starts ingestion service (port 8001)
- Starts Celery worker
- Starts all 3 MCP services (ports 8081-8083)
- Sets correct environment variables for local development
- Creates timestamped logs
- Tracks PIDs for easy shutdown

### 2. `stop-services.sh`
Graceful shutdown script that:
- Stops all running services by PID
- Cleans up remaining processes
- Kills processes by port if needed
- Removes PID files

### 3. `check-services.sh`
Service health check script that:
- Checks Docker services status
- Checks HTTP endpoints
- Verifies ports are in use
- Tests Celery worker
- Lists available logs
- Shows all service URLs

### 4. Documentation Files

#### `QUICK_START.md`
- Quick reference for starting/stopping services
- Service URLs table
- Common commands
- Troubleshooting tips

#### `START_SERVICES_GUIDE.md`
- Comprehensive guide
- Individual service startup instructions
- Detailed troubleshooting
- Production deployment notes

#### `ISSUES_RESOLVED.md` (this file)
- All issues found and fixed
- Step-by-step solutions
- Verification commands

---

## 🎯 How to Use the New Scripts

### Start Everything
```bash
# Start all services (ingestion, celery, mcp*)
./start-services.sh
```

### Check Status
```bash
# Verify all services are running
./check-services.sh
```

### Stop Everything
```bash
# Gracefully stop all services
./stop-services.sh
```

---

## 📊 Service Architecture

```
AgentMesh Services (Local Development)
├── Docker Services (always running)
│   ├── PostgreSQL (5432)
│   ├── Redis (6379)
│   ├── OpenSearch (9200)
│   ├── MinIO (9000, 9001)
│   ├── Phoenix (6006, 4317, 4318)
│   ├── Neo4j (7474, 7687)
│   ├── LiteLLM (4000)
│   └── MongoDB (27017)
│
├── Local Services (started by script)
│   ├── Ingestion Service (8001)
│   │   └── FastAPI app with Swagger docs
│   ├── Celery Worker
│   │   └── Processes ingestion tasks
│   ├── MCP Documents (8081)
│   ├── MCP Search (8082)
│   └── MCP Memory (8083)
│
└── Optional (start separately)
    ├── Backend API (8000)
    └── Frontend (8080)
```

---

## 🔍 Logs Location

All logs are stored in `logs/` directory with timestamps:

```
logs/
├── ingestion_20260908.log
├── celery_20260908.log
├── mcp_documents_20260908.log
├── mcp_search_20260908.log
├── mcp_memory_20260908.log
├── backend_20260908.log
└── frontend_20260908.log
```

View logs:
```bash
# Real-time monitoring
tail -f logs/ingestion_*.log
tail -f logs/celery_*.log

# View all logs
ls -lht logs/
```

---

## ✅ Verification Checklist

After running `./start-services.sh`, verify:

- [ ] Ingestion Service: http://localhost:8001/health returns `{"status":"healthy"}`
- [ ] Ingestion Docs: http://localhost:8001/docs shows Swagger UI
- [ ] Phoenix UI: http://localhost:6006 shows dashboard
- [ ] MCP Documents: Port 8081 is listening
- [ ] MCP Search: Port 8082 is listening  
- [ ] MCP Memory: Port 8083 is listening
- [ ] Celery Worker: `celery -A app.worker.celery_app inspect ping` returns pong
- [ ] Logs: Files created in `logs/` directory

---

## 🚀 Next Steps

1. **Test Document Upload**
   ```bash
   # Upload a test document via ingestion service
   curl -X POST http://localhost:8001/api/v1/ingest \
     -H "Content-Type: application/json" \
     -d '{"file_id":"test123","filename":"test.pdf","user_id":"user1"}'
   ```

2. **Monitor Tasks**
   ```bash
   # Check Celery worker active tasks
   cd agentservices/ingestion/ingestion-service
   source .venv/bin/activate
   celery -A app.worker.celery_app inspect active
   ```

3. **View Traces in Phoenix**
   - Open http://localhost:6006
   - See AI agent traces and performance metrics

4. **Test Backend API**
   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **Test Frontend**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

---

## 📞 Support

If you encounter any issues:

1. Check logs: `ls -lht logs/`
2. Run health check: `./check-services.sh`
3. Stop and restart: `./stop-services.sh && ./start-services.sh`
4. Check Docker services: `docker compose ps`
5. View Docker logs: `docker compose logs -f`

---

**All issues have been resolved and the services are now properly configured and documented!** ✅
