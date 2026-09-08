# Scripts Directory

This directory contains all automation scripts for AgentMesh local development.

## Available Scripts

### 🚀 start-local.sh
**Purpose:** Start infrastructure and setup local development environment

**What it does:**
1. Checks prerequisites (Docker, Python, Node.js)
2. Creates `.env` files for all services
3. Starts Docker infrastructure (PostgreSQL, Redis, OpenSearch, etc.)
4. Sets up Python virtual environments
5. Installs dependencies
6. Runs database migrations
7. Shows instructions for starting applications

**Usage:**
```bash
./start-local.sh
# Or from root:
cd /path/to/agentmesh && ./start-local.sh
```

**Time:** ~2-3 minutes first time, ~30 seconds subsequent runs

---

### 🛑 stop-local.sh
**Purpose:** Stop all Docker infrastructure services

**What it does:**
1. Stops all containers from docker-compose-infra.yml
2. Leaves volumes intact (data preserved)

**Usage:**
```bash
./stop-local.sh
# Or:
./scripts/stop-local.sh
```

**To remove data:**
```bash
docker compose -f docker-compose-infra.yml down -v
```

---

### 📤 export-env.sh
**Purpose:** Export environment variables to current shell

**What it does:**
- Exports all environment variables needed for local development
- Loads API keys from root `.env` file
- Sets infrastructure hosts to `localhost`

**Usage:**
```bash
source ./scripts/export-env.sh
# Or:
. ./scripts/export-env.sh

# Then run applications:
cd backend && uvicorn app.main:app --reload
```

**Note:** Must use `source` or `.` to affect current shell

---

### 🔍 check-status.sh
**Purpose:** Check status of all services

**What it does:**
1. Shows Docker container status
2. Tests connections to all services
3. Displays service URLs

**Usage:**
```bash
./check-status.sh
# Or:
./scripts/check-status.sh
```

**Example Output:**
```
✅ PostgreSQL: Connected
✅ Redis: Connected
✅ OpenSearch: Running
✅ MinIO: Healthy
✅ Phoenix: Healthy
```

---

## Script Launchers (in root)

For convenience, there are launcher scripts in the project root that call the actual scripts in this directory:

```
agentmesh/
├── start-local.sh      → scripts/start-local.sh
├── stop-local.sh       → scripts/stop-local.sh
├── check-status.sh     → scripts/check-status.sh
└── scripts/
    ├── start-local.sh  (actual script)
    ├── stop-local.sh   (actual script)
    ├── check-status.sh (actual script)
    └── export-env.sh   (source this one)
```

**This means you can run from anywhere:**
```bash
# From project root
./start-local.sh

# From scripts folder
cd scripts && ./start-local.sh

# Both work the same way!
```

---

## Environment Files Created

The `start-local.sh` script creates `.env` files in:

1. `backend/.env`
2. `agentservices/ingestion/ingestion-service/.env`
3. `agentservices/mcp/mcp-documents/.env`
4. `agentservices/mcp/mcp-search/.env`
5. `agentservices/mcp/mcp-memory/.env`

**Each file contains:**
- Infrastructure connection settings (with `localhost` and correct ports)
- Agent configuration
- API keys (copied from root `.env`)

**To regenerate:**
```bash
rm backend/.env agentservices/ingestion/ingestion-service/.env
./start-local.sh
```

---

## Important Notes

### PostgreSQL Port
PostgreSQL runs on port **5433** (not 5432) to avoid conflict with local PostgreSQL installation.

All `.env` files are automatically configured with:
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
```

### API Keys
API keys are copied from root `.env` file. Make sure you have:
```bash
# In agentmesh/.env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
TAVILY_API_KEY=tvly-...
```

### Virtual Environments
Scripts automatically create Python virtual environments:
- `backend/.venv`
- `agentservices/ingestion/ingestion-service/.venv`
- `agentservices/mcp/*/. venv`

---

## Troubleshooting

### Script won't run
```bash
chmod +x scripts/*.sh
```

### Can't find .env file
```bash
# Check if root .env exists
ls -la .env

# Regenerate service .env files
rm backend/.env
./start-local.sh
```

### Database connection fails
```bash
# Check port (should be 5433, not 5432)
cat backend/.env | grep POSTGRES_PORT

# Should show: POSTGRES_PORT=5433
```

### xargs error
This is fixed in current version. If you see it, update scripts:
```bash
git pull origin main
# Or re-download scripts
```

---

## Script Maintenance

### Adding a new service
1. Update `create_local_env()` function in `start-local.sh`
2. Add service path to the list of services
3. Test with `./start-local.sh`

### Changing environment variables
1. Update `.env.local` template (in project root)
2. Update `create_local_env()` in `start-local.sh`
3. Update `export-env.sh`
4. Regenerate all .env files

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `./start-local.sh` | Start everything |
| `./stop-local.sh` | Stop infrastructure |
| `./check-status.sh` | Check what's running |
| `source export-env.sh` | Load env vars to shell |

---

## Related Documentation

- [../FINAL_SETUP_SUCCESS.md](../FINAL_SETUP_SUCCESS.md) - Complete setup guide
- [../QUICK_START.md](../QUICK_START.md) - Quick reference
- [../LOCAL_INSTALL.md](../LOCAL_INSTALL.md) - Detailed installation
- [../ENV_SETUP_GUIDE.md](../ENV_SETUP_GUIDE.md) - Environment variables

---

**Last Updated:** 2026-09-08
