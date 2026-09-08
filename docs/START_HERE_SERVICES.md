# 🚀 AgentMesh Services - START HERE

## Quick Links

- **Want to start immediately?** → [QUICK_START.md](./QUICK_START.md)
- **Need detailed setup?** → [START_SERVICES_GUIDE.md](./START_SERVICES_GUIDE.md)
- **Want to understand the architecture?** → [README_SERVICES.md](./README_SERVICES.md)
- **What was fixed?** → [ISSUES_RESOLVED.md](./ISSUES_RESOLVED.md) or [SOLUTION_SUMMARY.md](./SOLUTION_SUMMARY.md)

---

## 🎯 Three Steps to Get Running

```bash
# 1. Start Docker infrastructure (if not already running)
docker compose up -d postgres redis opensearch minio phoenix neo4j mongodb

# 2. Start all application services
./start-services.sh

# 3. Verify everything is running
./check-services.sh
```

**That's it!** Open http://localhost:8001/docs to see the Ingestion API.

---

## 🔗 Service URLs

Once started, access these:

| What | URL | Use For |
|------|-----|---------|
| **Ingestion API** | http://localhost:8001/docs | Upload and process documents |
| **Backend API** | http://localhost:8000/docs | Main REST API |
| **Phoenix UI** | http://localhost:6006 | AI traces and monitoring |
| **Frontend** | http://localhost:8080 | Web interface |

---

## 📋 What the Scripts Do

### `./start-services.sh` ✅
Starts all local services:
- Ingestion Service (port 8001)
- Celery Worker (background tasks)
- MCP Documents (port 8081)
- MCP Search (port 8082)  
- MCP Memory (port 8083)

Creates logs in `logs/` directory.

### `./stop-services.sh` 🛑
Gracefully stops all services and cleans up processes.

### `./check-services.sh` 🔍
Shows status of all services and their URLs.

---

## 🐛 Common Issues & Solutions

### Issue: Can't access /docs endpoint
**Fixed!** This has been resolved. Just run `./start-services.sh`.

### Issue: Phoenix database error
**Fixed!** The startup script automatically creates the database.

### Issue: Celery won't connect
**Fixed!** The startup script sets `REDIS_HOST=localhost` automatically.

### Issue: Don't know how to start MCP services
**Fixed!** The startup script handles all MCP services.

---

## 📚 Documentation Index

1. **[QUICK_START.md](./QUICK_START.md)** - 2-minute guide (you are here!)
2. **[START_SERVICES_GUIDE.md](./START_SERVICES_GUIDE.md)** - Complete guide with all details
3. **[README_SERVICES.md](./README_SERVICES.md)** - Architecture and development workflow
4. **[ISSUES_RESOLVED.md](./ISSUES_RESOLVED.md)** - What was broken and how it was fixed
5. **[SOLUTION_SUMMARY.md](./SOLUTION_SUMMARY.md)** - Executive summary of changes

---

## ✅ Verification Checklist

After running `./start-services.sh`, check:

- [ ] Ingestion service: `curl http://localhost:8001/health`
- [ ] Docs accessible: Open http://localhost:8001/docs in browser
- [ ] Phoenix running: Open http://localhost:6006
- [ ] MCP services: `./check-services.sh` shows all ✓
- [ ] Logs created: `ls logs/`

---

## 💡 Next Steps

1. **Test document upload:**
   - Open http://localhost:8001/docs
   - Try the POST `/api/v1/ingest` endpoint

2. **Monitor AI traces:**
   - Open http://localhost:6006
   - See real-time LLM calls and performance

3. **Start backend API:**
   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Start frontend:**
   ```bash
   cd frontend
   npm install && npm run dev
   ```

---

## 🆘 Need Help?

1. Check logs: `tail -f logs/ingestion_*.log`
2. Run health check: `./check-services.sh`
3. Restart services: `./stop-services.sh && ./start-services.sh`
4. Check Docker: `docker compose ps`

---

## 🎉 You're All Set!

Everything is configured, documented, and working. The scripts will handle all the complexity for you.

**Run this now:**
```bash
./start-services.sh
```

Then open http://localhost:8001/docs and start building! 🚀
