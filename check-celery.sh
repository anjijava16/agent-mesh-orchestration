#!/bin/bash
# Quick Celery health check script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/agentservices/ingestion/ingestion-service"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}         Celery Worker Health Check           ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}\n"

# 1. Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${RED}✗ Virtual environment not found${NC}"
    echo -e "  Run: ./start-services.sh"
    exit 1
fi

source .venv/bin/activate

# Set environment variables for local development
export REDIS_HOST=localhost
export POSTGRES_HOST=localhost
export OPENSEARCH_HOST=localhost

# 2. Check Redis connection
echo -e "${YELLOW}[1/5] Checking Redis connection...${NC}"
if docker exec agentmesh-redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
    echo -e "${GREEN}✓ Redis is running${NC}"
else
    echo -e "${RED}✗ Redis is not accessible${NC}"
    echo -e "  Start Redis: docker compose up -d redis"
    exit 1
fi

# 3. Check if Celery process is running
echo -e "\n${YELLOW}[2/5] Checking Celery process...${NC}"
if ps aux | grep -v grep | grep "celery.*app.worker.celery_app" > /dev/null; then
    PID=$(ps aux | grep -v grep | grep "celery.*app.worker.celery_app" | awk '{print $2}' | head -1)
    echo -e "${GREEN}✓ Celery worker is running (PID: $PID)${NC}"
else
    echo -e "${RED}✗ Celery worker process not found${NC}"
    echo -e "  Start Celery: ./start-services.sh"
    exit 1
fi

# 4. Ping Celery worker
echo -e "\n${YELLOW}[3/5] Pinging Celery worker...${NC}"
if celery -A app.worker.celery_app inspect ping -t 5 2>&1 | grep -q "pong"; then
    echo -e "${GREEN}✓ Celery worker is responding${NC}"
else
    echo -e "${RED}✗ Celery worker is not responding${NC}"
    echo -e "  Check logs: tail -f logs/celery_*.log"
    exit 1
fi

# 5. Check registered tasks
echo -e "\n${YELLOW}[4/5] Checking registered tasks...${NC}"
TASKS=$(celery -A app.worker.celery_app inspect registered 2>&1 | grep "app.worker.tasks" | wc -l)
if [ "$TASKS" -gt 0 ]; then
    echo -e "${GREEN}✓ Found $TASKS registered task(s)${NC}"
    celery -A app.worker.celery_app inspect registered 2>&1 | grep "app.worker.tasks" | sed 's/^/  /'
else
    echo -e "${YELLOW}⚠ No tasks registered (worker may still be starting)${NC}"
fi

# 6. Check worker stats
echo -e "\n${YELLOW}[5/5] Worker statistics...${NC}"
STATS=$(celery -A app.worker.celery_app inspect stats 2>&1)
if echo "$STATS" | grep -q "OK"; then
    echo -e "${GREEN}✓ Worker statistics available${NC}"
    
    # Extract key info
    POOL=$(echo "$STATS" | grep "pool" | head -1 | sed 's/^[[:space:]]*/  /')
    CONCURRENCY=$(echo "$STATS" | grep "pool-max-concurrency" | head -1 | sed 's/^[[:space:]]*/  /')
    
    [ -n "$POOL" ] && echo "$POOL"
    [ -n "$CONCURRENCY" ] && echo "$CONCURRENCY"
else
    echo -e "${YELLOW}⚠ Could not retrieve worker stats${NC}"
fi

# 7. Check active tasks
echo -e "\n${YELLOW}Active Tasks:${NC}"
ACTIVE=$(celery -A app.worker.celery_app inspect active 2>&1 | grep -A 2 "name")
if [ -n "$ACTIVE" ]; then
    echo "$ACTIVE" | sed 's/^/  /'
else
    echo -e "  ${GREEN}No tasks currently running${NC}"
fi

# Summary
echo -e "\n${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Celery worker is healthy and ready!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "\nTo submit a test task:"
echo -e "  curl -X POST http://localhost:8001/api/v1/ingest \\"
echo -e "    -H 'Content-Type: application/json' \\"
echo -e "    -d '{\"file_id\":\"test\",\"filename\":\"test.pdf\",\"user_id\":\"user1\"}'"
echo -e "\nTo monitor tasks:"
echo -e "  tail -f logs/celery_*.log"
echo -e "\nFor more info:"
echo -e "  See CHECK_CELERY.md"

deactivate
