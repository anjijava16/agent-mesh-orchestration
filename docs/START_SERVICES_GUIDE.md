# AgentMesh Services Startup Guide

This guide explains how to start all AgentMesh services properly.

## Overview

AgentMesh consists of multiple services that need to be started in the correct order:

1. **Docker Services** (PostgreSQL, Redis, OpenSearch, MinIO, Phoenix, Neo4j, etc.)
2. **Ingestion Service** (Port 8001)
3. **Celery Worker** (Background task processing)
4. **MCP Services** (Ports 8081, 8082, 8083)
5. **Backend API** (Port 8000)
6. **Frontend** (Port 8080)

## Quick Start

### Option 1: Start Everything with Docker (Recommended)

```bash
# Start all services via docker-compose
docker compose up -d --build

# Check service health
docker compose ps

# Access services:
# - Frontend: http://localhost:8080
# - Backend: http://localhost:8000/docs
# - Phoenix: http://localhost:6006
# - OpenSearch: http://localhost:9200
```

### Option 2: Start Local Services (Development)

For local development with hot-reloading:

```bash
# 1. Start Docker infrastructure only
docker compose up -d postgres redis opensearch minio phoenix neo4j litellm mongodb

# 2. Stop all local services first
./stop-services.sh

# 3. Start all local services
./start-services.sh
```

## Individual Service Startup

### 1. Ingestion Service (Port 8001)

```bash
cd agentservices/ingestion/ingestion-service

# Create virtual environment if not exists
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start service
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Test
curl http://localhost:8001/health
# Open API docs: http://localhost:8001/docs
```

### 2. Celery Worker

```bash
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate

# Start worker
celery -A app.worker.celery_app worker \
    --loglevel=INFO \
    --concurrency=2 \
    -Q ingest,default \
    --max-tasks-per-child=50

# Check worker status
celery -A app.worker.celery_app inspect ping
```

### 3. MCP Services

#### MCP Documents (Port 8081)
```bash
cd agentservices/mcp/mcp-documents
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.server
```

#### MCP Search (Port 8082)
```bash
cd agentservices/mcp/mcp-search
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.server
```

#### MCP Memory (Port 8083)
```bash
cd agentservices/mcp/mcp-memory
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.server
```

### 4. Backend API (Port 8000)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Test
curl http://localhost:8000/api/v1/health/live
# API docs: http://localhost:8000/docs
```

### 5. Frontend (Port 8080)

```bash
cd frontend
npm install
npm run dev
# Opens on http://localhost:5173

# Or for production build:
npm run build
npm run preview
```

## Troubleshooting

### Phoenix Database Error

If you see: `asyncpg.exceptions.InvalidCatalogNameError: database "phoenix" does not exist`

**Fix:**
```bash
docker exec agentmesh-postgres psql -U agentmesh -d agentmesh -c "CREATE DATABASE phoenix;"
docker restart agentmesh-phoenix
```

### Ingestion Service /docs Not Working

The issue is fixed! Make sure you're using the latest code with FastAPI docs URLs configured.

### Port Already in Use

```bash
# Check what's using a port
lsof -i :8001

# Kill process on port
lsof -ti :8001 | xargs kill -9
```

### Celery Worker Not Starting

```bash
# Kill existing workers
pkill -9 -f "celery.*app.worker.celery_app"

# Check Redis connection
docker exec -it agentmesh-redis redis-cli ping
# Should return: PONG

# Restart worker
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate
celery -A app.worker.celery_app worker --loglevel=INFO
```

### MCP Services Not Starting

```bash
# Check logs in logs/ directory
tail -f logs/mcp_documents_*.log
tail -f logs/mcp_search_*.log
tail -f logs/mcp_memory_*.log

# Ensure PostgreSQL and OpenSearch are running
docker ps | grep -E "(postgres|opensearch)"
```

## Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:8080 | Main UI |
| Backend API | http://localhost:8000 | REST API |
| Backend Docs | http://localhost:8000/docs | Interactive API docs |
| Ingestion Service | http://localhost:8001 | File processing service |
| Ingestion Docs | http://localhost:8001/docs | Ingestion API docs |
| MCP Documents | http://localhost:8081 | Document management |
| MCP Search | http://localhost:8082 | Search service |
| MCP Memory | http://localhost:8083 | Memory service |
| Phoenix UI | http://localhost:6006 | AI Observability |
| OpenSearch | http://localhost:9200 | Search & vector store |
| OpenSearch Dashboards | http://localhost:5601 | OpenSearch UI |
| MinIO Console | http://localhost:9001 | S3-compatible storage |
| Neo4j Browser | http://localhost:7474 | Graph database UI |
| LiteLLM UI | http://localhost:4000/ui | LLM gateway |
| Flower | http://localhost:5555 | Celery monitoring |

## Logs

All logs are stored in the `logs/` directory:

```bash
# View logs
tail -f logs/ingestion_*.log
tail -f logs/celery_*.log
tail -f logs/backend_*.log
tail -f logs/mcp_documents_*.log

# Docker logs
docker compose logs -f backend
docker compose logs -f phoenix
docker compose logs -f ingestion-service
```

## Stopping Services

### Stop Docker Services
```bash
docker compose down
# Or to remove volumes:
docker compose down -v
```

### Stop Local Services
```bash
./stop-services.sh
```

## Common Commands

```bash
# Health check all services
curl http://localhost:8000/api/v1/health/live  # Backend
curl http://localhost:8001/health              # Ingestion
curl http://localhost:6006/healthz             # Phoenix

# Check Celery workers
celery -A app.worker.celery_app inspect active

# View Celery flower (monitoring UI)
docker compose --profile tools up -d flower
# Open http://localhost:5555

# Database migrations
cd backend
alembic upgrade head
alembic current

# Reset database (DANGER!)
docker compose down -v
docker compose up -d postgres
docker compose exec backend alembic upgrade head
```

## Environment Variables

Make sure your `.env` file is configured correctly. Key variables:

```bash
# API Keys
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here

# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=agentmesh
POSTGRES_PASSWORD=agentmesh
POSTGRES_DB=agentmesh

# Services
PHOENIX_ENABLED=true
LITELLM_ENABLED=true
```

## Development Workflow

1. Start infrastructure: `docker compose up -d postgres redis opensearch minio phoenix`
2. Start backend: `cd backend && uvicorn app.main:app --reload`
3. Start services: `./start-services.sh`
4. Start frontend: `cd frontend && npm run dev`
5. Code and test
6. Stop: `./stop-services.sh`

## Production Deployment

For production, use Docker Compose with all services:

```bash
# Start everything
docker compose up -d --build

# Check health
docker compose ps

# View logs
docker compose logs -f

# Scale workers
docker compose up -d --scale celery-worker=4
```

---

**Need Help?**
- Check logs in `logs/` directory
- Review service health: `docker compose ps`
- Verify environment variables in `.env`
- Ensure all required ports are free (8000, 8001, 8080, 8081, 8082, 8083)
