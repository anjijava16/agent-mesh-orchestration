#!/bin/bash
# Check status of all AgentMesh services

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   AgentMesh Service Status Check              ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}\n"

# Function to check HTTP service
check_http() {
    local name=$1
    local url=$2
    
    if curl -sf "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $name: Running${NC} ($url)"
        return 0
    else
        echo -e "${RED}✗ $name: Not responding${NC} ($url)"
        return 1
    fi
}

# Function to check port
check_port() {
    local name=$1
    local port=$2
    
    if lsof -i ":$port" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $name: Running on port $port${NC}"
        return 0
    else
        echo -e "${RED}✗ $name: Port $port not in use${NC}"
        return 1
    fi
}

# Function to check Docker service
check_docker() {
    local name=$1
    local container=$2
    
    if docker ps --filter "name=$container" --filter "status=running" | grep -q "$container"; then
        local health=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "unknown")
        if [ "$health" = "healthy" ] || [ "$health" = "unknown" ]; then
            echo -e "${GREEN}✓ $name: Running${NC}"
        else
            echo -e "${YELLOW}⚠ $name: Running but unhealthy${NC}"
        fi
        return 0
    else
        echo -e "${RED}✗ $name: Not running${NC}"
        return 1
    fi
}

echo -e "${YELLOW}Docker Services:${NC}"
check_docker "PostgreSQL" "agentmesh-postgres"
check_docker "Redis" "agentmesh-redis"
check_docker "OpenSearch" "agentmesh-opensearch"
check_docker "MinIO" "agentmesh-minio"
check_docker "Phoenix" "agentmesh-phoenix"
check_docker "Neo4j" "agentmesh-neo4j"
check_docker "LiteLLM" "agentmesh-litellm"
check_docker "MongoDB" "agentmesh-mongodb"

echo -e "\n${YELLOW}Backend Services:${NC}"
check_http "Backend API" "http://localhost:8000/api/v1/health/live"
check_http "Ingestion Service" "http://localhost:8001/health"

echo -e "\n${YELLOW}MCP Services:${NC}"
check_port "MCP Documents" 8081
check_port "MCP Search" 8082
check_port "MCP Memory" 8083

echo -e "\n${YELLOW}Celery Worker:${NC}"
cd "$(dirname "$0")/agentservices/ingestion/ingestion-service"
if [ -d ".venv" ]; then
    source .venv/bin/activate
    if celery -A app.worker.celery_app inspect ping 2>&1 | grep -q "pong"; then
        echo -e "${GREEN}✓ Celery Worker: Responding${NC}"
    else
        echo -e "${RED}✗ Celery Worker: Not responding${NC}"
    fi
    deactivate
else
    echo -e "${RED}✗ Celery Worker: Virtual environment not found${NC}"
fi

echo -e "\n${YELLOW}Web UIs:${NC}"
echo -e "  Frontend:           http://localhost:8080"
echo -e "  Backend API Docs:   http://localhost:8000/docs"
echo -e "  Ingestion Docs:     http://localhost:8001/docs"
echo -e "  Phoenix UI:         http://localhost:6006"
echo -e "  OpenSearch UI:      http://localhost:5601"
echo -e "  MinIO Console:      http://localhost:9001"
echo -e "  Neo4j Browser:      http://localhost:7474"
echo -e "  LiteLLM UI:         http://localhost:4000/ui"

echo -e "\n${YELLOW}Logs:${NC}"
LOG_DIR="$(dirname "$0")/logs"
if [ -d "$LOG_DIR" ]; then
    echo -e "  ${GREEN}Available log files:${NC}"
    ls -lht "$LOG_DIR"/*.log 2>/dev/null | head -10 | awk '{print "  " $9}'
else
    echo -e "  ${YELLOW}No logs directory found${NC}"
fi

echo -e "\n${GREEN}════════════════════════════════════════════════${NC}"
