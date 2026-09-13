#!/bin/bash
# Check all AgentMesh service URLs

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   AgentMesh Services Status Check             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo ""

check_url() {
    local name=$1
    local url=$2
    local desc=$3
    
    if curl -sf "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $name${NC}"
        echo -e "  ${BLUE}$url${NC}"
        echo -e "  $desc"
    else
        echo -e "${RED}✗ $name (NOT RUNNING)${NC}"
        echo -e "  ${YELLOW}$url${NC}"
        echo -e "  $desc"
    fi
    echo ""
}

echo -e "${BLUE}🎨 User Interfaces:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_url "Frontend UI" "http://localhost:5173" "Main application interface"
check_url "Phoenix UI" "http://localhost:6006" "AI observability dashboard"
check_url "LiteLLM UI" "http://localhost:4000/ui" "LLM gateway dashboard"
check_url "OpenSearch Dashboards" "http://localhost:5601" "Search analytics"
check_url "Neo4j Browser" "http://localhost:7474" "Graph database UI"
check_url "MinIO Console" "http://localhost:9001" "Object storage UI"

echo -e "${BLUE}🔧 API Services:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_url "Backend API" "http://localhost:8000/api/v1/health/live" "Main backend API"
check_url "Backend Docs" "http://localhost:8000/docs" "API documentation"
check_url "Ingestion API" "http://localhost:8001/health" "Document ingestion"
check_url "Ingestion Docs" "http://localhost:8001/docs" "Ingestion API docs"

echo -e "${BLUE}🛠️  MCP Services:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_url "MCP Documents" "http://localhost:8081/health" "Document management"
check_url "MCP Search" "http://localhost:8082/health" "Search service"
check_url "MCP Memory" "http://localhost:8083/health" "Memory service"

echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}💡 To start services: ./start-services.sh${NC}"
echo -e "${YELLOW}💡 To start with logs: ./start-services-with-logs.sh${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
