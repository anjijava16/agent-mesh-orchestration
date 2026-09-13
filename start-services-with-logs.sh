#!/bin/bash
# Complete startup script for AgentMesh with VISIBLE LOGS
# This script shows startup logs in console AND saves them to logs/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Log directory
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
DATE=$(date +%Y%m%d_%H%M%S)

echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   AgentMesh Services Startup with Logs        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📝 All logs will be shown here AND saved to logs/${NC}"
echo ""

# Function to check port
check_port() {
    lsof -i ":$1" >/dev/null 2>&1
}

# Function to kill port
kill_port() {
    local port=$1
    if check_port $port; then
        echo -e "${YELLOW}⚠️  Killing process on port $port${NC}"
        lsof -ti ":$port" | xargs kill -9 2>/dev/null || true
        sleep 2
    fi
}

# Function to run service with visible logs (background with tee)
run_service() {
    local name=$1
    local port=$2
    local cmd=$3
    local logfile="$LOG_DIR/${name}_${DATE}.log"
    
    echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}🚀 Starting: $name (Port: $port)${NC}"
    echo -e "${YELLOW}📝 Logs: $logfile${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # Run command in background, tee to log file and show initial output
    (eval "$cmd" 2>&1 | tee "$logfile") &
    local pid=$!
    echo $pid > "$LOG_DIR/${name}.pid"
    
    echo -e "${GREEN}✓ Started with PID: $pid${NC}"
    echo -e "${BLUE}💡 View live logs: tail -f $logfile${NC}"
    sleep 2
}

# 1. Check infrastructure
echo -e "${BLUE}[1/7] Checking Docker infrastructure...${NC}"
if ! docker ps | grep -q agentmesh-postgres; then
    echo -e "${RED}❌ Docker infrastructure not running!${NC}"
    echo -e "${YELLOW}Run: docker compose -f docker-compose-infra.yml up -d${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Infrastructure running${NC}"

# 2. Fix Phoenix database
echo -e "\n${BLUE}[2/7] Checking Phoenix database...${NC}"
docker exec agentmesh-postgres psql -U agentmesh -d agentmesh -c "SELECT 1 FROM pg_database WHERE datname = 'phoenix';" 2>/dev/null | grep -q 1 && {
    echo -e "${GREEN}✓ Phoenix database exists${NC}"
} || {
    echo -e "${YELLOW}Creating Phoenix database...${NC}"
    docker exec agentmesh-postgres psql -U agentmesh -d agentmesh -c "CREATE DATABASE phoenix;" 2>/dev/null || true
    docker restart agentmesh-phoenix
    sleep 5
}

# Set environment for local services
export REDIS_HOST=localhost
export POSTGRES_HOST=localhost
export OPENSEARCH_HOST=localhost
export LITELLM_BASE_URL=http://localhost:4000

# 3. Start Ingestion Service
echo -e "\n${BLUE}[3/7] Starting Ingestion Service...${NC}"
kill_port 8001

cd "$SCRIPT_DIR/agentservices/ingestion/ingestion-service"
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

INGESTION_CMD="uvicorn app.main:app --host 0.0.0.0 --port 8001 --log-level info"
run_service "ingestion" "8001" "$INGESTION_CMD"

cd "$SCRIPT_DIR"
deactivate

# 4. Start Celery Worker
echo -e "\n${BLUE}[4/7] Starting Celery Worker...${NC}"
pkill -9 -f "celery.*app.worker.celery_app" 2>/dev/null || true
sleep 2

cd "$SCRIPT_DIR/agentservices/ingestion/ingestion-service"
source .venv/bin/activate

CELERY_CMD="celery -A app.worker.celery_app worker --loglevel=INFO --concurrency=2 -Q ingest,default --max-tasks-per-child=50"
run_service "celery" "N/A" "$CELERY_CMD"

cd "$SCRIPT_DIR"
deactivate

# 5. Start MCP Documents
echo -e "\n${BLUE}[5/7] Starting MCP Documents (8081)...${NC}"
kill_port 8081

cd "$SCRIPT_DIR/agentservices/mcp/mcp-documents"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

export MCP_SERVER_PORT=8081
MCP_DOC_CMD="python -m app.server"
run_service "mcp_documents" "8081" "$MCP_DOC_CMD"

cd "$SCRIPT_DIR"
deactivate

# 6. Start MCP Search
echo -e "\n${BLUE}[6/7] Starting MCP Search (8082)...${NC}"
kill_port 8082

cd "$SCRIPT_DIR/agentservices/mcp/mcp-search"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

export MCP_SERVER_PORT=8082
MCP_SEARCH_CMD="python -m app.server"
run_service "mcp_search" "8082" "$MCP_SEARCH_CMD"

cd "$SCRIPT_DIR"
deactivate

# 7. Start MCP Memory
echo -e "\n${BLUE}[7/7] Starting MCP Memory (8083)...${NC}"
kill_port 8083

cd "$SCRIPT_DIR/agentservices/mcp/mcp-memory"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

export MCP_SERVER_PORT=8083
MCP_MEM_CMD="python -m app.server"
run_service "mcp_memory" "8083" "$MCP_MEM_CMD"

cd "$SCRIPT_DIR"
deactivate

# Wait for services to start
echo -e "\n${BLUE}⏳ Waiting for services to initialize...${NC}"
sleep 10

# Verify services
echo -e "\n${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Service Status Check                        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"

check_service() {
    local name=$1
    local url=$2
    if curl -sf "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $name: RUNNING${NC}"
    else
        echo -e "${YELLOW}⚠ $name: STARTING...${NC}"
    fi
}

check_service "Ingestion Service" "http://localhost:8001/health"
check_service "MCP Documents" "http://localhost:8081/health"
check_service "MCP Search" "http://localhost:8082/health"
check_service "MCP Memory" "http://localhost:8083/health"

if celery -A app.worker.celery_app inspect ping 2>/dev/null | grep -q pong; then
    echo -e "${GREEN}✓ Celery Worker: RUNNING${NC}"
else
    echo -e "${YELLOW}⚠ Celery Worker: STARTING...${NC}"
fi

# Display summary
echo -e "\n${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Services URLs                                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo -e "📥 Ingestion:       ${BLUE}http://localhost:8001${NC}"
echo -e "📄 Ingestion Docs:  ${BLUE}http://localhost:8001/docs${NC}"
echo -e "📄 MCP Documents:   ${BLUE}http://localhost:8081${NC}"
echo -e "🔍 MCP Search:      ${BLUE}http://localhost:8082${NC}"
echo -e "🧠 MCP Memory:      ${BLUE}http://localhost:8083${NC}"
echo -e "🚀 Backend:         ${BLUE}http://localhost:8000${NC}"
echo -e "🎨 Frontend:        ${BLUE}http://localhost:5173${NC}"
echo -e "🐦 Phoenix:         ${BLUE}http://localhost:6006${NC}"

echo -e "\n${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Log Files                                    ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo -e "📝 All logs in: ${YELLOW}$LOG_DIR/${NC}"
ls -1 "$LOG_DIR"/*.log 2>/dev/null | tail -10 | while read log; do
    echo -e "   • $(basename $log)"
done

echo -e "\n${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Monitor Logs                                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo -e "Watch all logs: ${YELLOW}tail -f $LOG_DIR/*_${DATE}.log${NC}"
echo -e "Watch ingestion: ${YELLOW}tail -f $LOG_DIR/ingestion_${DATE}.log${NC}"
echo -e "Watch celery: ${YELLOW}tail -f $LOG_DIR/celery_${DATE}.log${NC}"

echo -e "\n${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Stop Services                                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo -e "${YELLOW}./stop-services.sh${NC}"

echo -e "\n${GREEN}✅ All services started! Logs are being saved and displayed.${NC}"
echo -e "${BLUE}💡 Press Ctrl+C in each terminal to stop individual services${NC}"
