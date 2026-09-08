#!/bin/bash
# Complete startup script for AgentMesh services
# This script starts all local services (ingestion, celery, mcp services)

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Log directory
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
DATE=$(date +%Y%m%d)

echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   AgentMesh Services Startup                   ║${NC}"
echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"

# Function to check if port is in use
check_port() {
    lsof -i ":$1" >/dev/null 2>&1
}

# Function to kill process on port
kill_port() {
    local port=$1
    if check_port $port; then
        echo -e "${YELLOW}Killing process on port $port${NC}"
        lsof -ti ":$port" | xargs kill -9 2>/dev/null || true
        sleep 2
    fi
}

# 1. Fix Phoenix database issue
echo -e "\n${GREEN}[1/6] Checking Phoenix database...${NC}"
docker exec -it agentmesh-postgres psql -U agentmesh -d agentmesh -c "SELECT 1 FROM pg_database WHERE datname = 'phoenix';" | grep -q 1 && {
    echo -e "${GREEN}✓ Phoenix database exists${NC}"
} || {
    echo -e "${YELLOW}Creating Phoenix database...${NC}"
    docker exec -it agentmesh-postgres psql -U agentmesh -d agentmesh -c "CREATE DATABASE phoenix;" || true
}

# Restart Phoenix service
echo -e "${YELLOW}Restarting Phoenix service...${NC}"
docker restart agentmesh-phoenix
sleep 5

# 2. Start Ingestion Service
echo -e "\n${GREEN}[2/6] Starting Ingestion Service...${NC}"
kill_port 8001

cd "$SCRIPT_DIR/agentservices/ingestion/ingestion-service"
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Override Redis host for local development
export REDIS_HOST=localhost
export POSTGRES_HOST=localhost
export OPENSEARCH_HOST=localhost

echo -e "${GREEN}Starting ingestion service on port 8001...${NC}"
nohup uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8001 \
    --log-level info \
    > "$LOG_DIR/ingestion_${DATE}.log" 2>&1 &

INGESTION_PID=$!
echo $INGESTION_PID > "$LOG_DIR/ingestion.pid"
echo -e "${GREEN}✓ Ingestion service started (PID: $INGESTION_PID)${NC}"
sleep 3

# 3. Start Celery Worker
echo -e "\n${GREEN}[3/6] Starting Celery Worker...${NC}"

# Kill existing celery workers
pkill -9 -f "celery.*app.worker.celery_app" || true
sleep 2

# Ensure environment variables are set for local development
export REDIS_HOST=localhost
export POSTGRES_HOST=localhost
export OPENSEARCH_HOST=localhost

echo -e "${GREEN}Starting celery worker...${NC}"
nohup celery -A app.worker.celery_app worker \
    --loglevel=INFO \
    --concurrency=2 \
    -Q ingest,default \
    --max-tasks-per-child=50 \
    > "$LOG_DIR/celery_${DATE}.log" 2>&1 &

CELERY_PID=$!
echo $CELERY_PID > "$LOG_DIR/celery.pid"
echo -e "${GREEN}✓ Celery worker started (PID: $CELERY_PID)${NC}"

cd "$SCRIPT_DIR"
deactivate

# 4. Start MCP Services
echo -e "\n${GREEN}[4/6] Starting MCP Services...${NC}"

# Override environment for local MCP services
export REDIS_HOST=localhost
export POSTGRES_HOST=localhost
export OPENSEARCH_HOST=localhost

# MCP Documents (port 8081)
echo -e "${YELLOW}Starting MCP Documents service (port 8081)...${NC}"
kill_port 8081

cd "$SCRIPT_DIR/agentservices/mcp/mcp-documents"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

nohup python -m app.server \
    > "$LOG_DIR/mcp_documents_${DATE}.log" 2>&1 &

MCP_DOC_PID=$!
echo $MCP_DOC_PID > "$LOG_DIR/mcp_documents.pid"
echo -e "${GREEN}✓ MCP Documents started (PID: $MCP_DOC_PID)${NC}"
deactivate

# MCP Search (port 8082)
echo -e "${YELLOW}Starting MCP Search service (port 8082)...${NC}"
kill_port 8082

cd "$SCRIPT_DIR/agentservices/mcp/mcp-search"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

nohup python -m app.server \
    > "$LOG_DIR/mcp_search_${DATE}.log" 2>&1 &

MCP_SEARCH_PID=$!
echo $MCP_SEARCH_PID > "$LOG_DIR/mcp_search.pid"
echo -e "${GREEN}✓ MCP Search started (PID: $MCP_SEARCH_PID)${NC}"
deactivate

# MCP Memory (port 8083)
echo -e "${YELLOW}Starting MCP Memory service (port 8083)...${NC}"
kill_port 8083

cd "$SCRIPT_DIR/agentservices/mcp/mcp-memory"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

nohup python -m app.server \
    > "$LOG_DIR/mcp_memory_${DATE}.log" 2>&1 &

MCP_MEM_PID=$!
echo $MCP_MEM_PID > "$LOG_DIR/mcp_memory.pid"
echo -e "${GREEN}✓ MCP Memory started (PID: $MCP_MEM_PID)${NC}"
deactivate

cd "$SCRIPT_DIR"

# 5. Wait and verify services
echo -e "\n${GREEN}[5/6] Verifying services...${NC}"
sleep 5

# Check ingestion service
if curl -s http://localhost:8001/health | grep -q "healthy"; then
    echo -e "${GREEN}✓ Ingestion Service: http://localhost:8001 ${NC}"
    echo -e "${GREEN}  Docs: http://localhost:8001/docs ${NC}"
else
    echo -e "${RED}✗ Ingestion Service failed to start${NC}"
fi

# Check celery worker
if celery -A app.worker.celery_app inspect ping -d "celery@$(hostname)" 2>/dev/null | grep -q "pong"; then
    echo -e "${GREEN}✓ Celery Worker: Running${NC}"
else
    echo -e "${YELLOW}⚠ Celery Worker: Starting (may take a moment)${NC}"
fi

# Check MCP services
for port in 8081 8082 8083; do
    if check_port $port; then
        echo -e "${GREEN}✓ MCP Service on port $port: Running${NC}"
    else
        echo -e "${RED}✗ MCP Service on port $port: Failed${NC}"
    fi
done

# 6. Display status
echo -e "\n${GREEN}[6/6] Service Status Summary${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "Ingestion Service:  http://localhost:8001"
echo -e "Ingestion API Docs: http://localhost:8001/docs"
echo -e "MCP Documents:      http://localhost:8081"
echo -e "MCP Search:         http://localhost:8082"
echo -e "MCP Memory:         http://localhost:8083"
echo -e "Backend API:        http://localhost:8000"
echo -e "Phoenix UI:         http://localhost:6006"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "\nLogs are in: $LOG_DIR/"
echo -e "To stop services: ./stop-services.sh"
echo -e "\n${GREEN}All services started successfully!${NC}"
