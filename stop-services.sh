#!/bin/bash
# Stop all AgentMesh local services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Stopping AgentMesh Services...${NC}"

# Function to stop service by PID file
stop_service() {
    local name=$1
    local pid_file="$LOG_DIR/${name}.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            echo -e "${YELLOW}Stopping $name (PID: $pid)...${NC}"
            kill -15 $pid 2>/dev/null || kill -9 $pid 2>/dev/null
            sleep 1
        fi
        rm -f "$pid_file"
        echo -e "${GREEN}✓ $name stopped${NC}"
    fi
}

# Stop services
stop_service "ingestion"
stop_service "celery"
stop_service "mcp_documents"
stop_service "mcp_search"
stop_service "mcp_memory"

# Kill any remaining processes
echo -e "\n${YELLOW}Cleaning up remaining processes...${NC}"
pkill -9 -f "uvicorn app.main:app.*8001" 2>/dev/null || true
pkill -9 -f "celery.*app.worker.celery_app" 2>/dev/null || true
pkill -9 -f "python.*mcp.*server" 2>/dev/null || true

# Kill by port
for port in 8001 8081 8082 8083; do
    if lsof -i ":$port" >/dev/null 2>&1; then
        echo -e "${YELLOW}Killing process on port $port${NC}"
        lsof -ti ":$port" | xargs kill -9 2>/dev/null || true
    fi
done

echo -e "\n${GREEN}All services stopped successfully!${NC}"
