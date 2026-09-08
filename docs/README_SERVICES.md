# AgentMesh Services - Complete Guide

## 🎯 Overview

AgentMesh consists of multiple microservices that work together:

1. **Ingestion Service** (Port 8001) - Document processing and embedding generation
2. **Celery Worker** - Background task processing for ingestion
3. **MCP Services** - Three Model Context Protocol servers:
   - MCP Documents (8081) - Document management
   - MCP Search (8082) - Web and corpus search
   - MCP Memory (8083) - Long-term memory storage
4. **Backend API** (Port 8000) - Main REST API
5. **Frontend** (Port 8080) - Web interface

## 🚀 Quick Start (3 Commands)

```bash
# 1. Start Docker infrastructure
docker compose up -d postgres redis opensearch minio phoenix neo4j litellm mongodb

# 2. Start all local services (ingestion, celery, mcp*)
./start-services.sh

# 3. Check everything is running
./check-services.sh
```

That's it! Open http://localhost:8001/docs to see the ingestion API.

## 📋 What Each Script Does

### `./start-services.sh`
✅ **Automatically handles:**
- Creates Phoenix database if missing
- Starts Ingestion Service on port 8001
- Starts Celery worker for background tasks
- Starts all 3 MCP services (ports 8081-8083)
- Sets correct environment variables for local development
- Creates timestamped log files
- Tracks process IDs for clean shutdown

### `./stop-services.sh`
🛑 **Gracefully stops:**
- All local services (ingestion, celery, mcp*)
- Kills stuck processes
- Cleans up PID files

### `./check-services.sh`
🔍 **Verifies:**
- Docker services health
- HTTP endpoints responding
- Ports are listening
- Celery worker status
- Shows service URLs and logs

## 📊 Service URLs Reference

| Service | URL | Purpose |
|---------|-----|---------|
| **Ingestion API Docs** | http://localhost:8001/docs | 📄 File upload and processing API |
| **Ingestion Health** | http://localhost:8001/health | ✅ Service health check |
| **Backend API Docs** | http://localhost:8000/docs | 📚 Main REST API documentation |
| **Phoenix UI** | http://localhost:6006 | 🔍 AI traces and observability |
| **OpenSearch** | http://localhost:9200 | 🔎 Vector and full-text search |
| **OpenSearch Dashboards** | http://localhost:5601 | 📊 OpenSearch UI |
| **MinIO Console** | http://localhost:9001 | 💾 S3-compatible storage UI |
| **Neo4j Browser** | http://localhost:7474 | 🕸️ Graph database UI |
| **Frontend** | http://localhost:8080 | 🌐 Main web interface |

## 🔧 Development Workflow

### Starting Fresh Each Day

```bash
# Check what's running
docker compose ps

# Start infrastructure if needed
docker compose up -d postgres redis opensearch minio phoenix

# Start application services
./start-services.sh

# Verify everything is up
./check-services.sh
```

### Making Changes to Code

All services support hot-reload:

```bash
# Edit code in:
# - agentservices/ingestion/ingestion-service/
# - agentservices/mcp/mcp-documents/
# - agentservices/mcp/mcp-search/
# - agentservices/mcp/mcp-memory/

# No restart needed - changes auto-reload!
```

### Viewing Logs

```bash
# Real-time log monitoring
tail -f logs/ingestion_*.log
tail -f logs/celery_*.log
tail -f logs/mcp_documents_*.log

# View all recent logs
ls -lht logs/
```

### Stopping for the Day

```bash
# Stop local services
./stop-services.sh

# Optionally stop Docker (or leave running)
docker compose down
```

## 🐛 Troubleshooting

### Issue: Port Already in Use

```bash
# Check what's using port 8001
lsof -i :8001

# Kill it
lsof -ti :8001 | xargs kill -9

# Or use the stop script
./stop-services.sh
```

### Issue: Service Not Responding

```bash
# 1. Check logs
tail -f logs/ingestion_*.log

# 2. Restart the service
./stop-services.sh
./start-services.sh

# 3. Check Docker services
docker compose ps
docker compose logs -f postgres redis
```

### Issue: Celery Worker Not Connecting

```bash
# Ensure Redis is running
docker exec -it agentmesh-redis redis-cli ping
# Should return: PONG

# Check Celery logs
tail -f logs/celery_*.log

# Restart
./stop-services.sh
./start-services.sh
```

### Issue: Phoenix Database Error

This is automatically fixed by `start-services.sh`, but if you see errors:

```bash
# Manually create database
docker exec agentmesh-postgres psql -U agentmesh -d agentmesh -c "CREATE DATABASE phoenix;"

# Restart Phoenix
docker restart agentmesh-phoenix
```

### Issue: Can't Access /docs Endpoint

**Fixed!** The issue was that FastAPI docs URLs weren't explicitly configured. This has been resolved in the latest code.

```bash
# Verify it works
curl http://localhost:8001/docs | grep "Swagger UI"
```

## 📝 Testing the System

### 1. Test Ingestion Service

```bash
# Health check
curl http://localhost:8001/health

# Test document ingestion (after uploading to MinIO)
curl -X POST http://localhost:8001/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "test123",
    "filename": "test.pdf",
    "user_id": "user1",
    "vector_backend": "opensearch",
    "chunk_size": 512,
    "chunk_overlap": 50
  }'

# Response will include task_id
```

### 2. Check Celery Task Status

```bash
# Get task status
curl http://localhost:8001/api/v1/tasks/{task_id}
```

### 3. Monitor in Phoenix

1. Open http://localhost:6006
2. View traces from LLM calls
3. See ingestion pipeline execution

## 🔑 Environment Variables

Services read from `.env` in the root directory:

```bash
# Required API Keys
OPENAI_API_KEY=sk-...           # For embeddings
ANTHROPIC_API_KEY=sk-ant-...    # For Claude models
GOOGLE_API_KEY=...              # For Gemini models (optional)
TAVILY_API_KEY=...              # For web search (optional)

# Database (defaults work for Docker)
POSTGRES_HOST=postgres
REDIS_HOST=redis
OPENSEARCH_HOST=opensearch

# For local development, these are overridden to 'localhost' by start-services.sh
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│  Frontend (React)        :8080                  │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│  Backend API (FastAPI)   :8000                  │
│  ├── Chat endpoints                             │
│  ├── File management                            │
│  └── Agent orchestration                        │
└────────────────┬────────────────────────────────┘
                 │
    ┌────────────┼────────────┬─────────────┐
    │            │            │             │
┌───▼──┐   ┌────▼───┐   ┌────▼───┐   ┌────▼────┐
│ MCP  │   │  MCP   │   │  MCP   │   │Ingestion│
│ Docs │   │ Search │   │ Memory │   │ Service │
│:8081 │   │  :8082 │   │  :8083 │   │  :8001  │
└──────┘   └────────┘   └────────┘   └─────┬───┘
                                            │
                                      ┌─────▼────┐
                                      │  Celery  │
                                      │  Worker  │
                                      └──────────┘
                      │
    ┌─────────────────┼─────────────────────┐
    │                 │                     │
┌───▼─────┐   ┌───────▼────┐   ┌───────────▼─────┐
│Postgres │   │ OpenSearch │   │  Redis / MinIO  │
│  :5432  │   │   :9200    │   │ :6379 / :9000   │
└─────────┘   └────────────┘   └─────────────────┘
```

## 📚 Additional Documentation

- **[QUICK_START.md](./QUICK_START.md)** - Minimal quick reference
- **[START_SERVICES_GUIDE.md](./START_SERVICES_GUIDE.md)** - Detailed guide with troubleshooting
- **[ISSUES_RESOLVED.md](./ISSUES_RESOLVED.md)** - All fixed issues documented
- **[README.md](./README.md)** - Original project README

## 🎓 Common Tasks

### Upload and Process a Document

```bash
# 1. Upload file to MinIO (or use UI)
# 2. Trigger ingestion
curl -X POST http://localhost:8001/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"file_id":"abc123","filename":"doc.pdf","user_id":"user1"}'

# 3. Check task status
curl http://localhost:8001/api/v1/tasks/TASK_ID_HERE

# 4. View in Phoenix
open http://localhost:6006
```

### Query Documents via Backend

```bash
# Search documents
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query":"your search query","top_k":5}'

# Chat with documents
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What are the key points?","conversation_id":"conv123"}'
```

### Monitor Celery Tasks

```bash
# Active tasks
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate
celery -A app.worker.celery_app inspect active

# Worker stats
celery -A app.worker.celery_app inspect stats

# Registered tasks
celery -A app.worker.celery_app inspect registered
```

## 🚀 Production Deployment

For production, use Docker Compose for everything:

```bash
# Build and start all services
docker compose up -d --build

# Scale workers
docker compose up -d --scale celery-worker=4

# View logs
docker compose logs -f

# Stop everything
docker compose down
```

## ✅ Success Criteria

After running `./start-services.sh`, you should see:

```
✓ Ingestion Service: http://localhost:8001 
  Docs: http://localhost:8001/docs 
✓ Celery Worker: Running
✓ MCP Service on port 8081: Running
✓ MCP Service on port 8082: Running
✓ MCP Service on port 8083: Running
```

Open http://localhost:8001/docs and you should see the Swagger UI with endpoints:
- POST `/api/v1/ingest` - Trigger document ingestion
- GET `/api/v1/tasks/{task_id}` - Check task status
- DELETE `/api/v1/documents/{file_id}` - Purge document
- GET `/health` - Health check

---

**Everything is now properly configured and documented!** 🎉

For questions or issues, check the logs in `logs/` directory or run `./check-services.sh`.
