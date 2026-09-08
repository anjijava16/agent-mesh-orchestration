# Environment Variables - Quick Cheatsheet

## 🎯 Docker vs Local

| Service | Docker Hostname | Local Hostname | Port |
|---------|----------------|----------------|------|
| PostgreSQL | `postgres` | `localhost` | 5432 |
| Redis | `redis` | `localhost` | 6379 |
| OpenSearch | `opensearch` | `localhost` | 9200 |
| MinIO | `minio` | `localhost` | 9000 |
| Phoenix | `phoenix` | `localhost` | 4317/6006 |
| Neo4j | `neo4j` | `localhost` | 7687 |
| LiteLLM | `litellm` | `localhost` | 4000 |
| MongoDB | `mongodb` | `localhost` | 27017 |

## 🚀 Quick Start

### Method 1: Automatic (Easiest)
```bash
./start-local.sh
# Creates .env files in all service directories
```

### Method 2: Shell Export
```bash
source export-env.sh
cd backend && uvicorn app.main:app --reload
```

### Method 3: Manual .env
```bash
cp .env.local backend/.env
# Edit as needed
```

## 📋 Essential Variables

### Database
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=agentmesh
POSTGRES_PASSWORD=agentmesh
POSTGRES_DB=agentmesh
```

### OpenSearch
```bash
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=Agentmesh#2026
```

### Redis
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
```

### MinIO
```bash
STORAGE_ENDPOINT_URL=http://localhost:9000
STORAGE_ACCESS_KEY=minioadmin
STORAGE_SECRET_KEY=minioadmin
```

### Phoenix
```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

### API Keys (from .env)
```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
TAVILY_API_KEY=tvly-...
```

## 🔧 Common Commands

### Check Variables
```bash
# After sourcing
echo $POSTGRES_HOST
echo $OPENAI_API_KEY
```

### Test Connections
```bash
curl http://localhost:6006/healthz          # Phoenix
curl http://localhost:9200                  # OpenSearch
redis-cli -h localhost -p 6379 ping        # Redis
psql -h localhost -U agentmesh -d agentmesh # PostgreSQL
```

### View .env Files
```bash
cat backend/.env
cat agentservices/ingestion/ingestion-service/.env
```

## ⚠️ Common Mistakes

### ❌ Wrong
```bash
POSTGRES_HOST=postgres          # Docker hostname
REDIS_HOST=redis                # Docker hostname
export OPENAI_API_KEY           # Missing value
./export-env.sh                 # Run instead of source
```

### ✅ Correct
```bash
POSTGRES_HOST=localhost         # Host access
REDIS_HOST=localhost            # Host access
export OPENAI_API_KEY=sk-...    # With value
source export-env.sh            # Source, not run
```

## 🎨 Terminal Setup

### Backend
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### Ingestion Service
```bash
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate
uvicorn app.main:app --reload --port 8001
```

### Celery Worker
```bash
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate
celery -A app.worker.celery_app worker --loglevel=INFO
```

### Frontend
```bash
cd frontend
npm run dev
```

## 📂 File Locations

```
agentmesh/
├── .env                      # API keys (git-ignored)
├── .env.local               # Template
├── export-env.sh            # Shell export script
├── start-local.sh           # Auto-setup script
├── backend/.env             # Auto-created
├── agentservices/
│   └── ingestion/
│       └── ingestion-service/.env  # Auto-created
└── ENV_SETUP_GUIDE.md       # Full documentation
```

## 🐛 Debugging

### Not Connecting?
1. Check hostname is `localhost` not docker name
2. Check port matches docker-compose-infra.yml
3. Verify service is running: `docker ps`

### API Key Missing?
1. Add to root `.env` file
2. Re-run `./start-local.sh`
3. Or manually add to service `.env`

### Wrong Values?
1. Delete service `.env` files
2. Re-run `./start-local.sh`
3. Or use `source export-env.sh`

## 🔗 Quick Links

- Full Guide: [ENV_SETUP_GUIDE.md](ENV_SETUP_GUIDE.md)
- Local Install: [LOCAL_INSTALL.md](LOCAL_INSTALL.md)
- Quick Start: [QUICK_START.md](QUICK_START.md)

---

**TL;DR:** Run `./start-local.sh` and everything is configured automatically! 🎉
