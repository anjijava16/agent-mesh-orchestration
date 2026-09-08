# Local Development Setup

This guide shows how to run **infrastructure services** (OpenSearch, MinIO, PostgreSQL, Redis, Phoenix, Neo4j) in Docker while running **application services** (Backend, Frontend, MCP servers, Ingestion service) locally on your machine.

**Benefits:**
- 💡 Faster development iterations (no container rebuilds)
- 🚀 Lower resource usage (Docker only for infrastructure)
- 🔥 Hot reload support for code changes
- 🐛 Easier debugging with direct Python access

---

## Prerequisites

- **Python 3.12** (recommended)
- **Node.js 18+** and **npm** (for frontend)
- **Docker** and **Docker Compose** (for infrastructure)
- **uv** or **pip** (Python package manager)

---

## 1. Infrastructure Services (Docker)

Run only the infrastructure services in Docker using the dedicated compose file:

```bash
# Start infrastructure services
docker compose -f docker-compose-infra.yml up -d

# Or use the convenience script
./start-local.sh
```

**Services started:**
- **PostgreSQL**: `localhost:5432`
- **Redis**: `localhost:6379`
- **OpenSearch**: `localhost:9200`
- **OpenSearch Dashboards**: `localhost:5601`
- **MinIO**: `localhost:9000` (Console: `localhost:9001`)
- **MongoDB**: `localhost:27017`
- **Neo4j**: `localhost:7474` (Bolt: `localhost:7687`)
- **Phoenix (Arize)**: `localhost:6006` (OTLP: `localhost:4317`, `localhost:4318`)
- **LiteLLM**: `localhost:4000`

### Verify Infrastructure

```bash
# Check all services are healthy
docker compose -f docker-compose-infra.yml ps

# View logs
docker compose -f docker-compose-infra.yml logs -f postgres

# Stop services
docker compose -f docker-compose-infra.yml down

# Stop and remove volumes (delete all data)
docker compose -f docker-compose-infra.yml down -v
```

---

## 2. Environment Setup

Create a `.env` file in the project root (copy from `.env.example`):

```bash
cp .env.example .env
```

**Important:** Update these for local development:

```bash
# Database (localhost since running locally)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=agentmesh
POSTGRES_PASSWORD=agentmesh
POSTGRES_DB=agentmesh

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# OpenSearch
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=Agentmesh#2026
OPENSEARCH_USE_SSL=false

# MinIO/S3
STORAGE_ENDPOINT_URL=http://localhost:9000
STORAGE_ACCESS_KEY=minioadmin
STORAGE_SECRET_KEY=minioadmin
STORAGE_BUCKET=agentmesh-uploads

# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=agentmesh

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=agentmesh

# Phoenix (Arize)
PHOENIX_HOST=localhost
PHOENIX_GRPC_PORT=4317
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# LiteLLM
LITELLM_BASE_URL=http://localhost:4000
LITELLM_MASTER_KEY=sk-agentmesh-local

# API Keys (add your own)
OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
GOOGLE_API_KEY=your-google-api-key
TAVILY_API_KEY=your-tavily-api-key

# MCP Servers (will run locally)
MCP_DOCUMENTS_URL=http://localhost:8081
MCP_SEARCH_URL=http://localhost:8082
MCP_MEMORY_URL=http://localhost:8083

# Ingestion Service (will run locally)
INGESTION_SERVICE_URL=http://localhost:8001
```

---

## 3. Backend Service (Local)

### Setup

```bash
cd backend

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # On macOS/Linux
# .venv\Scripts\activate   # On Windows

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head
```

### Run Backend

```bash
# Make sure .venv is activated
source .venv/bin/activate

# Run with hot reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Or with multiple workers (production-like)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

**Backend available at:** `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/api/v1/health/live`

---

## 4. Ingestion Service (Local)

### Setup

```bash
cd agentservices/ingestion/ingestion-service

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations (uses same DB as backend)
alembic upgrade head
```

### Run Ingestion Service

```bash
# Activate virtual environment
source .venv/bin/activate

# Run FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

**Ingestion Service available at:** `http://localhost:8001`
- Health Check: `http://localhost:8001/health`

### Run Celery Worker (for file processing)

In a **separate terminal**:

```bash
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate

# Run Celery worker
celery -A app.worker.celery_app worker \
  --loglevel=INFO \
  --concurrency=2 \
  -Q ingest,default \
  --max-tasks-per-child=50
```

### Optional: Run Flower (Celery Monitoring)

In a **separate terminal**:

```bash
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate

# Run Flower
celery -A app.worker.celery_app flower --port=5555
```

**Flower UI:** `http://localhost:5555`

---

## 5. Frontend (Local)

### Setup

```bash
cd frontend

# Install dependencies
npm install
```

### Run Frontend

```bash
# Development mode with hot reload
npm run dev

# Or production build + preview
npm run build
npm run preview
```

**Frontend available at:** `http://localhost:5173` (dev) or `http://localhost:8080` (preview)

---

## 6. MCP Servers (Local)

### MCP Documents Server

```bash
cd agentservices/mcp/mcp-documents

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run server
python -m app.server
```

**Available at:** `http://localhost:8081`

### MCP Search Server

```bash
cd agentservices/mcp/mcp-search

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run server
python -m app.server
```

**Available at:** `http://localhost:8082`

### MCP Memory Server

```bash
cd agentservices/mcp/mcp-memory

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run server
python -m app.server
```

**Available at:** `http://localhost:8083`

---

## 7. Development Workflow

### Terminal Setup (Recommended)

Use **tmux** or multiple terminal tabs:

1. **Terminal 1**: Infrastructure (Docker)
   ```bash
   docker compose up postgres redis opensearch minio neo4j phoenix mongodb litellm
   ```

2. **Terminal 2**: Backend
   ```bash
   cd backend && source .venv/bin/activate
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Terminal 3**: Ingestion Service API
   ```bash
   cd agentservices/ingestion/ingestion-service && source .venv/bin/activate
   uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
   ```

4. **Terminal 4**: Celery Worker
   ```bash
   cd agentservices/ingestion/ingestion-service && source .venv/bin/activate
   celery -A app.worker.celery_app worker --loglevel=INFO --concurrency=2 -Q ingest,default
   ```

5. **Terminal 5**: Frontend
   ```bash
   cd frontend
   npm run dev
   ```

6. **Terminal 6**: MCP Documents
   ```bash
   cd agentservices/mcp/mcp-documents && source .venv/bin/activate
   python -m app.server
   ```

7. **Terminal 7**: MCP Search
   ```bash
   cd agentservices/mcp/mcp-search && source .venv/bin/activate
   python -m app.server
   ```

8. **Terminal 8**: MCP Memory
   ```bash
   cd agentservices/mcp/mcp-memory && source .venv/bin/activate
   python -m app.server
   ```

### Using tmux (Recommended)

```bash
# Install tmux if not installed
brew install tmux  # macOS
# sudo apt install tmux  # Linux

# Start tmux session
tmux new -s agentmesh

# Split windows (Ctrl+b then ")
# Switch between panes (Ctrl+b then arrow keys)
# Detach: Ctrl+b then d
# Reattach: tmux attach -t agentmesh
```

---

## 8. Quick Start Script

Create `start-local.sh`:

```bash
#!/bin/bash

# Start infrastructure
echo "Starting infrastructure services..."
docker compose up -d postgres redis opensearch minio neo4j phoenix mongodb litellm

# Wait for services to be ready
echo "Waiting for services to be healthy..."
sleep 10

# Start backend
echo "Starting backend..."
cd backend && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start ingestion service
echo "Starting ingestion service..."
cd ../agentservices/ingestion/ingestion-service && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload &
INGESTION_PID=$!

# Start celery worker
echo "Starting celery worker..."
celery -A app.worker.celery_app worker --loglevel=INFO --concurrency=2 -Q ingest,default &
CELERY_PID=$!

# Start frontend
echo "Starting frontend..."
cd ../../../frontend
npm run dev &
FRONTEND_PID=$!

# Start MCP servers
echo "Starting MCP servers..."
cd ../agentservices/mcp/mcp-documents && source .venv/bin/activate
python -m app.server &
MCP_DOCS_PID=$!

cd ../mcp-search && source .venv/bin/activate
python -m app.server &
MCP_SEARCH_PID=$!

cd ../mcp-memory && source .venv/bin/activate
python -m app.server &
MCP_MEMORY_PID=$!

echo "All services started!"
echo "Backend: http://localhost:8000"
echo "Ingestion: http://localhost:8001"
echo "Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all services"

# Trap Ctrl+C and cleanup
trap "kill $BACKEND_PID $INGESTION_PID $CELERY_PID $FRONTEND_PID $MCP_DOCS_PID $MCP_SEARCH_PID $MCP_MEMORY_PID; docker compose down" EXIT

# Wait
wait
```

Make executable and run:

```bash
chmod +x start-local.sh
./start-local.sh
```

---

## 9. Stopping Services

### Stop Applications (Local)

```bash
# Press Ctrl+C in each terminal

# Or kill all processes
pkill -f "uvicorn app.main:app"
pkill -f "celery -A app"
pkill -f "npm run dev"
pkill -f "python -m app.server"
```

### Stop Infrastructure (Docker)

```bash
# Stop but keep data
docker compose stop postgres redis opensearch minio neo4j phoenix mongodb litellm

# Stop and remove containers (data persists in volumes)
docker compose down

# Stop and remove everything including data
docker compose down -v
```

---

## 10. Troubleshooting

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000
# Kill it
kill -9 <PID>
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check PostgreSQL logs
docker compose logs postgres

# Connect to database
docker compose exec postgres psql -U agentmesh -d agentmesh
```

### Python Dependencies Issues

```bash
# Clear pip cache and reinstall
pip cache purge
pip install -r requirements.txt --force-reinstall
```

### Frontend Build Issues

```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

---

## 11. VS Code Configuration

Create `.vscode/launch.json` for debugging:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Backend",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload", "--port", "8000"],
      "cwd": "${workspaceFolder}/backend",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/backend"
      }
    },
    {
      "name": "Ingestion Service",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload", "--port", "8001"],
      "cwd": "${workspaceFolder}/agentservices/ingestion/ingestion-service"
    },
    {
      "name": "Celery Worker",
      "type": "python",
      "request": "launch",
      "module": "celery",
      "args": ["-A", "app.worker.celery_app", "worker", "--loglevel=INFO"],
      "cwd": "${workspaceFolder}/agentservices/ingestion/ingestion-service"
    }
  ]
}
```

---

## 12. Resource Usage Comparison

### Docker (All Services)
- **Memory**: ~8-10 GB
- **CPU**: 4-6 cores actively used
- **Disk I/O**: High during builds

### Hybrid (Infrastructure in Docker + Apps Local)
- **Memory**: ~3-4 GB (Docker infrastructure only)
- **CPU**: 1-2 cores (infrastructure only)
- **Disk I/O**: Low (no app rebuilds)

**Savings:** ~50-60% memory, ~60-70% CPU

---

## 13. Production Deployment

When ready to deploy, build Docker images:

```bash
# Build all application images
docker compose build backend frontend ingestion-service

# Push to registry
docker tag agentmesh-backend your-registry/agentmesh-backend:latest
docker push your-registry/agentmesh-backend:latest
```

---

## Need Help?

- **API Documentation**: http://localhost:8000/docs
- **Backend Logs**: Check terminal running uvicorn
- **Database**: http://localhost:5432 (use pgAdmin or DBeaver)
- **OpenSearch**: http://localhost:5601 (Dashboards)
- **MinIO**: http://localhost:9001 (Console)
- **Phoenix (Observability)**: http://localhost:6006

---

**Happy Coding! 🚀**
