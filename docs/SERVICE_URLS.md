# AgentMesh Service URLs & Ports

## 🎨 Main User Interface (UI)

### **Frontend Application**
- **URL:** http://localhost:5173
- **Port:** 5173 (development) / 8080 (Docker production)
- **Description:** Main AgentMesh web application interface
- **Status:** ⚠️ Not running (needs to be started)

**How to Start:**
```bash
# Development mode
cd frontend
npm install
npm run dev

# Or using the script
scripts/run-frontend.sh
```

**Docker mode:**
```bash
docker compose up -d frontend
# Access at: http://localhost:8080
```

---

## 📊 Service Dashboard & URLs

### User Interfaces (Dashboards)

| Service | Port | URL | Description | Status |
|---------|------|-----|-------------|--------|
| **Frontend** | **5173** | **http://localhost:5173** | Main UI | ⚠️ Not Running |
| Phoenix | 6006 | http://localhost:6006 | AI Observability | ✅ Running |
| LiteLLM | 4000 | http://localhost:4000/ui | LLM Gateway | ✅ Running |
| OpenSearch | 5601 | http://localhost:5601 | Search Analytics | ✅ Running |
| Neo4j | 7474 | http://localhost:7474 | Graph Database | ✅ Running |
| MinIO | 9001 | http://localhost:9001 | Object Storage | ✅ Running |

### API Services

| Service | Port | URL | Documentation | Status |
|---------|------|-----|---------------|--------|
| Backend | 8000 | http://localhost:8000 | http://localhost:8000/docs | ✅ Running |
| Ingestion | 8001 | http://localhost:8001 | http://localhost:8001/docs | ✅ Running |

### MCP Services

| Service | Port | URL | Description | Status |
|---------|------|-----|-------------|--------|
| MCP Documents | 8081 | http://localhost:8081 | Document Management | ⚠️ Not Running |
| MCP Search | 8082 | http://localhost:8082 | Search Service | ⚠️ Not Running |
| MCP Memory | 8083 | http://localhost:8083 | Memory Service | ⚠️ Not Running |

---

## 🚀 Quick Access Commands

### Main Application
```bash
# Frontend UI (Main Interface)
open http://localhost:5173

# Backend API Documentation
open http://localhost:8000/docs

# Ingestion API Documentation
open http://localhost:8001/docs
```

### Monitoring & Dashboards
```bash
# Phoenix (AI Observability)
open http://localhost:6006

# LiteLLM (LLM Gateway)
open http://localhost:4000/ui

# OpenSearch Dashboards
open http://localhost:5601

# Neo4j Browser
open http://localhost:7474

# MinIO Console
open http://localhost:9001
```

---

## 🔧 Port Configuration

### Default Ports by Service

| Port | Service | Type | Description |
|------|---------|------|-------------|
| 5173 | Frontend | UI | React dev server |
| 8080 | Frontend | UI | Production Docker |
| 8000 | Backend | API | Main REST API |
| 8001 | Ingestion | API | Document ingestion |
| 8081 | MCP Documents | API | MCP Documents |
| 8082 | MCP Search | API | MCP Search |
| 8083 | MCP Memory | API | MCP Memory |
| 6006 | Phoenix | UI | AI observability |
| 4000 | LiteLLM | API/UI | LLM gateway |
| 5432 | PostgreSQL | DB | Database |
| 6379 | Redis | Cache | Cache/message broker |
| 9200 | OpenSearch | DB | Search engine |
| 5601 | Dashboards | UI | OpenSearch UI |
| 7474 | Neo4j | UI | Graph DB browser |
| 7687 | Neo4j | DB | Bolt protocol |
| 9000 | MinIO | API | Object storage |
| 9001 | MinIO | UI | Console |
| 27017 | MongoDB | DB | Document DB |

---

## 🏁 Starting Services

### Start All Services
```bash
# With visible logs (recommended)
./start-services-with-logs.sh

# Background mode
./start-services.sh
```

### Start Individual Services
```bash
# Frontend
scripts/run-frontend.sh         # http://localhost:5173

# Backend
scripts/run-backend.sh          # http://localhost:8000

# Ingestion
scripts/run-ingestion.sh        # http://localhost:8001

# MCP Services
scripts/run-mcp-documents.sh    # http://localhost:8081
scripts/run-mcp-search.sh       # http://localhost:8082
scripts/run-mcp-memory.sh       # http://localhost:8083

# Celery
scripts/run-celery.sh
```

---

## 🔍 Check Service Status

### Using the Check Script
```bash
./check-urls.sh
```

### Manual Checks
```bash
# Frontend
curl -I http://localhost:5173

# Backend
curl http://localhost:8000/api/v1/health/live

# Ingestion
curl http://localhost:8001/health

# Phoenix
curl http://localhost:6006/healthz

# LiteLLM
curl http://localhost:4000/health/liveliness

# MCP Services
curl http://localhost:8081/health
curl http://localhost:8082/health
curl http://localhost:8083/health
```

### Check Running Ports
```bash
# List all ports in use
lsof -i -P | grep LISTEN | grep -E "5173|8000|8001|8081|8082|8083|6006|4000"

# Check specific port
lsof -i :5173
lsof -i :8000
lsof -i :8001
```

---

## 🔐 Default Credentials

### Neo4j
- **URL:** http://localhost:7474
- **Username:** neo4j
- **Password:** agentmesh (or from .env: `NEO4J_PASSWORD`)

### MinIO
- **URL:** http://localhost:9001
- **Username:** minioadmin (or from .env: `STORAGE_ACCESS_KEY`)
- **Password:** minioadmin (or from .env: `STORAGE_SECRET_KEY`)

### LiteLLM
- **URL:** http://localhost:4000/ui
- **Username:** admin (from .env: `UI_USERNAME`)
- **Password:** admin (or from .env: `LITELLM_UI_PASSWORD`)

---

## 🌐 Docker vs Local Development

### Docker Mode (Full Stack)
```bash
docker compose up -d
```
**Access:**
- Frontend: http://localhost:8080
- Backend: http://localhost:8000
- All other services: same ports

### Local Development Mode
```bash
# Infrastructure in Docker
docker compose -f docker-compose-infra.yml up -d

# Services running locally
./start-services.sh
```
**Access:**
- Frontend: http://localhost:5173 (dev server)
- Backend: http://localhost:8000
- All other services: same ports

---

## 📱 Mobile/Remote Access

If accessing from another device on the same network:

```bash
# Find your local IP
ipconfig getifaddr en0  # macOS WiFi
# or
hostname -I  # Linux

# Access via IP
http://<YOUR_IP>:5173  # Frontend
http://<YOUR_IP>:8000  # Backend
http://<YOUR_IP>:6006  # Phoenix
```

**Note:** Update CORS settings in `.env` for remote access:
```bash
CORS_ORIGINS='["http://localhost:5173","http://<YOUR_IP>:5173"]'
```

---

## 🐛 Troubleshooting URLs

### Port Already in Use
```bash
# Find process using port
lsof -ti :5173

# Kill process
lsof -ti :5173 | xargs kill -9

# Or use the script
./start-services.sh  # Auto-kills existing processes
```

### Service Not Accessible
```bash
# Check if service is running
ps aux | grep node      # Frontend
ps aux | grep uvicorn   # Backend/Ingestion
ps aux | grep celery    # Celery

# Check logs
./view-logs.sh frontend -f
./view-logs.sh backend -f
./view-logs.sh ingestion -f

# Restart service
scripts/run-frontend.sh
scripts/run-backend.sh
```

### Wrong URL or Port
```bash
# Verify configuration
cat .env | grep PORT
cat frontend/vite.config.ts  # Frontend port config
cat backend/app/main.py      # Backend port config
```

---

## 📚 Related Documentation

- **Complete Guide:** `docs/COMPREHENSIVE_LOGGING_GUIDE.md`
- **Service Architecture:** `docs/README_SERVICES.md`
- **Getting Started:** `docs/START_HERE_SERVICES.md`
- **Troubleshooting:** `docs/ISSUES_RESOLVED.md`

---

## ✅ Quick Summary

**Main UI:** http://localhost:5173 (Frontend)  
**API Docs:** http://localhost:8000/docs (Backend)  
**Monitoring:** http://localhost:6006 (Phoenix)  
**Check Status:** `./check-urls.sh`  
**Start Services:** `./start-services-with-logs.sh`

---

**Last Updated:** September 8, 2026
