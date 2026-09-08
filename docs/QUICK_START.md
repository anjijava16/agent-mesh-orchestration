# AgentMesh Quick Start

## 🚀 Start All Services

```bash
# Option 1: Start local services (development mode with hot-reload)
./start-services.sh

# Option 2: Start everything with Docker (production-like)
docker compose up -d --build
```

## 🛑 Stop All Services

```bash
# Stop local services
./stop-services.sh

# Stop Docker services
docker compose down
```

## 📊 Service URLs

| Service | URL | Status |
|---------|-----|--------|
| **Frontend** | http://localhost:8080 | 🌐 Main UI |
| **Backend API** | http://localhost:8000/docs | 📚 REST API |
| **Ingestion Service** | http://localhost:8001/docs | 📄 File Processing |
| **Phoenix UI** | http://localhost:6006 | 🔍 AI Observability |
| **MCP Documents** | http://localhost:8081 | 📁 Documents |
| **MCP Search** | http://localhost:8082 | 🔎 Search |
| **MCP Memory** | http://localhost:8083 | 🧠 Memory |
| **OpenSearch** | http://localhost:9200 | 🔍 Vector Store |
| **MinIO Console** | http://localhost:9001 | 💾 Storage |

## 🔧 What Gets Started

### Local Development Mode (`./start-services.sh`)
1. ✅ **Phoenix Database** - Created if missing
2. ✅ **Ingestion Service** (Port 8001) - File processing API
3. ✅ **Celery Worker** - Background task processor
4. ✅ **MCP Documents** (Port 8081) - Document management
5. ✅ **MCP Search** (Port 8082) - Search functionality
6. ✅ **MCP Memory** (Port 8083) - Long-term memory

### Prerequisites (Docker must be running)
- PostgreSQL (Port 5432)
- Redis (Port 6379)
- OpenSearch (Port 9200)
- MinIO (Port 9000)
- Phoenix (Port 6006)
- Neo4j (Port 7474)

## 📝 Check Status

```bash
# Check all running processes
ps aux | grep -E "(celery|uvicorn|mcp)" | grep -v grep

# Check service health
curl http://localhost:8001/health
curl http://localhost:8000/api/v1/health/live

# Check Docker services
docker compose ps

# View logs
tail -f logs/ingestion_*.log
tail -f logs/celery_*.log
tail -f logs/mcp_*.log
```

## 🐛 Troubleshooting

### Issue: Ingestion service /docs not accessible
**Fixed!** The `/docs` endpoint is now properly configured.

### Issue: Phoenix database error
```bash
# Phoenix database "phoenix" does not exist
# Solution: The start script automatically creates it!
docker exec agentmesh-postgres psql -U agentmesh -d agentmesh -c "CREATE DATABASE phoenix;"
docker restart agentmesh-phoenix
```

### Issue: Port already in use
```bash
# Kill process on specific port
lsof -ti :8001 | xargs kill -9

# Or use the stop script
./stop-services.sh
```

### Issue: Celery worker not responding
```bash
# Check worker status
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate
celery -A app.worker.celery_app inspect ping

# Restart worker
./stop-services.sh
./start-services.sh
```

## 📚 Next Steps

1. **Upload a document**: http://localhost:8080
2. **Test ingestion API**: http://localhost:8001/docs
3. **Monitor AI traces**: http://localhost:6006
4. **Query documents**: http://localhost:8000/docs

## 🔑 Environment Variables

Make sure `.env` is configured with your API keys:

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
TAVILY_API_KEY=...  # Optional, for web search
```

## 📦 Installation (First Time)

```bash
# 1. Clone and navigate
cd agentmesh

# 2. Copy environment file
cp .env.example .env
# Edit .env with your API keys

# 3. Start Docker infrastructure
docker compose up -d postgres redis opensearch minio phoenix neo4j litellm mongodb

# 4. Wait for services to be healthy (30-60 seconds)
docker compose ps

# 5. Run database migrations
docker compose exec backend alembic upgrade head

# 6. Start local services
./start-services.sh

# 7. Start frontend (in new terminal)
cd frontend
npm install
npm run dev
```

## 💡 Tips

- Use `./start-services.sh` for development with hot-reload
- Use `docker compose up -d --build` for production-like testing
- Logs are in `logs/` directory with timestamps
- PIDs are tracked in `logs/*.pid` files
- All services auto-restart on crashes (when using Docker)

## 🆘 Need Help?

See the full guide: [START_SERVICES_GUIDE.md](./START_SERVICES_GUIDE.md)
