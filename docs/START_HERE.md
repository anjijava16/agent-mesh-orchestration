# 🚀 AgentMesh - Start Here!

## Quick Start (2 Steps)

### Step 1: Start Infrastructure

```bash
./start-local.sh
```

Wait ~30 seconds for services to be healthy.

### Step 2: Start Applications

**Option A: All at once with tmux (Recommended)**
```bash
./start-all-apps.sh
```

**Option B: Individual terminals**
```bash
# Terminal 1
./run-backend.sh

# Terminal 2
./run-frontend.sh
```

### Step 3: Access

**Frontend:** http://localhost:5173  
**Backend API:** http://localhost:8000/docs

---

## 📝 Automatic Logging

All services log to `logs/` directory with date stamps:

```
logs/backend_20260908.log
logs/frontend_20260908.log
logs/ingestion_20260908.log
logs/celery_20260908.log
logs/mcp_documents_20260908.log
logs/mcp_search_20260908.log
logs/mcp_memory_20260908.log
```

**View logs:**
```bash
tail -f logs/backend_$(date +%Y%m%d).log
tail -f logs/*.log  # All logs
```

---

## 🎮 Available Commands

| Command | Purpose |
|---------|---------|
| `./start-local.sh` | Start Docker infrastructure |
| `./start-all-apps.sh` | Start all apps with tmux + logging |
| `./run-backend.sh` | Start backend (with logging) |
| `./run-frontend.sh` | Start frontend (with logging) |
| `./run-ingestion.sh` | Start ingestion service |
| `./run-celery.sh` | Start Celery worker |
| `./stop-local.sh` | Stop infrastructure |
| `./check-status.sh` | Check service status |

---

## 📊 Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:5173 | Main UI |
| Backend API | http://localhost:8000 | REST API |
| API Docs | http://localhost:8000/docs | OpenAPI/Swagger |
| Ingestion | http://localhost:8001 | File processing |
| PostgreSQL | localhost:5433 | Database |
| Redis | localhost:6379 | Cache |
| OpenSearch | http://localhost:9200 | Search |
| MinIO Console | http://localhost:9001 | Storage UI |
| Phoenix | http://localhost:6006 | Observability |

---

## 🎯 Common Tasks

### View All Logs
```bash
tail -f logs/*.log
```

### Search Logs for Errors
```bash
grep -i error logs/*.log
```

### Restart a Service
```bash
# Stop it (Ctrl+C) then:
./run-backend.sh
```

### Check What's Running
```bash
./check-status.sh
```

### Stop Everything
```bash
# If using tmux:
tmux kill-session -t agentmesh

# Stop infrastructure:
./stop-local.sh
```

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| **[START_HERE.md](START_HERE.md)** | ⭐ This file - Quick start |
| **[FINAL_SETUP_SUCCESS.md](FINAL_SETUP_SUCCESS.md)** | Complete setup guide |
| **[LOGGING_GUIDE.md](LOGGING_GUIDE.md)** | Logging documentation |
| **[LOCAL_INSTALL.md](LOCAL_INSTALL.md)** | Detailed installation |
| **[ENV_SETUP_GUIDE.md](ENV_SETUP_GUIDE.md)** | Environment variables |
| **[ENV_CHEATSHEET.md](ENV_CHEATSHEET.md)** | Quick env reference |
| **[DOCKER_VS_LOCAL_ENV.md](DOCKER_VS_LOCAL_ENV.md)** | Docker vs Local |
| [scripts/README.md](scripts/README.md) | Scripts documentation |
| [notebook/README_PHOENIX.md](notebook/README_PHOENIX.md) | Phoenix observability |

---

## ⚠️  Important Notes

### PostgreSQL Port
PostgreSQL runs on port **5433** (not 5432) to avoid conflict with local PostgreSQL.

### API Keys
Add your API keys to `.env` file:
```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
TAVILY_API_KEY=tvly-...
```

### Tmux Controls
- **Detach:** `Ctrl+b` then `d`
- **Reattach:** `tmux attach -t agentmesh`
- **Kill:** `tmux kill-session -t agentmesh`
- **Navigate:** `Ctrl+b` then arrow keys

---

## 🐛 Troubleshooting

### Services Won't Start
```bash
# Check infrastructure
./check-status.sh

# Restart infrastructure
./stop-local.sh
./start-local.sh
```

### Can't Connect to Database
```bash
# Check PostgreSQL is on port 5433
docker ps | grep postgres

# Test connection
PGPASSWORD=agentmesh psql -h localhost -p 5433 -U agentmesh -d agentmesh -c "SELECT 1;"
```

### Logs Not Appearing
```bash
# Check logs directory exists
ls -la logs/

# Create if missing
mkdir -p logs
```

### Old .env Files
```bash
# Regenerate
rm backend/.env agentservices/ingestion/ingestion-service/.env
./start-local.sh
```

---

## 💡 Pro Tips

### 1. Install tmux for Better Experience
```bash
brew install tmux
```

### 2. View Logs in Real-time
```bash
tail -f logs/backend_$(date +%Y%m%d).log
```

### 3. Search Across All Logs
```bash
grep -r "error" logs/
```

### 4. Clean Old Logs
```bash
find logs/ -mtime +30 -delete
```

### 5. Use Aliases
Add to `~/.zshrc`:
```bash
alias am-start='cd ~/path/to/agentmesh && ./start-local.sh'
alias am-apps='cd ~/path/to/agentmesh && ./start-all-apps.sh'
alias am-logs='cd ~/path/to/agentmesh && tail -f logs/*.log'
alias am-stop='cd ~/path/to/agentmesh && ./stop-local.sh'
```

---

## ✅ Success Checklist

- [ ] Infrastructure started: `./start-local.sh`
- [ ] Services healthy: `./check-status.sh`
- [ ] Applications running: `./start-all-apps.sh`
- [ ] Frontend accessible: http://localhost:5173
- [ ] Backend accessible: http://localhost:8000/docs
- [ ] Logs being written: `ls -la logs/`

---

## 🎉 You're Ready!

Everything is configured and ready for development:
- ✅ Infrastructure in Docker (3-4GB RAM)
- ✅ Applications run locally with hot reload
- ✅ All logs dated and organized
- ✅ Tmux integration for easy management
- ✅ Complete documentation

**Happy coding! 🚀**

---

**Quick Help:**
- View this guide: `cat START_HERE.md`
- Check status: `./check-status.sh`
- View logs: `tail -f logs/*.log`
- Need help: See [FINAL_SETUP_SUCCESS.md](FINAL_SETUP_SUCCESS.md)
