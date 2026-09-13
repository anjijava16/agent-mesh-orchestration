#!/bin/bash
# View logs for AgentMesh services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

show_help() {
    echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   AgentMesh Log Viewer                        ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Usage: $0 [service] [options]"
    echo ""
    echo "Services:"
    echo "  all         - Watch all services logs"
    echo "  backend     - Backend service logs"
    echo "  frontend    - Frontend service logs"
    echo "  ingestion   - Ingestion service logs"
    echo "  celery      - Celery worker logs"
    echo "  mcp-docs    - MCP Documents service logs"
    echo "  mcp-search  - MCP Search service logs"
    echo "  mcp-memory  - MCP Memory service logs"
    echo ""
    echo "Options:"
    echo "  -f, --follow    Follow log output (like tail -f)"
    echo "  -n <lines>      Show last N lines (default: 50)"
    echo "  -l, --list      List all log files"
    echo ""
    echo "Examples:"
    echo "  $0 all -f                # Watch all logs"
    echo "  $0 backend -f            # Watch backend logs"
    echo "  $0 celery -n 100         # Show last 100 lines of celery"
    echo "  $0 -l                    # List all log files"
}

list_logs() {
    echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   Available Log Files                         ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
    echo ""
    
    if [ ! -d "$LOG_DIR" ]; then
        echo -e "${YELLOW}No logs directory found${NC}"
        return
    fi
    
    cd "$LOG_DIR"
    
    for service in backend frontend ingestion celery mcp_documents mcp_search mcp_memory; do
        latest=$(ls -t ${service}_*.log 2>/dev/null | head -1)
        if [ -n "$latest" ]; then
            size=$(du -h "$latest" | cut -f1)
            modified=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$latest" 2>/dev/null || stat -c "%y" "$latest" 2>/dev/null | cut -d. -f1)
            echo -e "${BLUE}$service${NC}"
            echo -e "  File: $latest"
            echo -e "  Size: $size"
            echo -e "  Modified: $modified"
            echo ""
        fi
    done
}

view_log() {
    local service=$1
    local follow=$2
    local lines=$3
    
    cd "$LOG_DIR"
    
    # Find latest log file for service
    local logfile
    case $service in
        backend)
            logfile=$(ls -t backend_*.log 2>/dev/null | head -1)
            ;;
        frontend)
            logfile=$(ls -t frontend_*.log 2>/dev/null | head -1)
            ;;
        ingestion)
            logfile=$(ls -t ingestion_*.log 2>/dev/null | head -1)
            ;;
        celery)
            logfile=$(ls -t celery_*.log 2>/dev/null | head -1)
            ;;
        mcp-docs|mcp_documents)
            logfile=$(ls -t mcp_documents_*.log 2>/dev/null | head -1)
            ;;
        mcp-search|mcp_search)
            logfile=$(ls -t mcp_search_*.log 2>/dev/null | head -1)
            ;;
        mcp-memory|mcp_memory)
            logfile=$(ls -t mcp_memory_*.log 2>/dev/null | head -1)
            ;;
        all)
            logfile="*_$(date +%Y%m%d)*.log"
            ;;
        *)
            echo -e "${YELLOW}Unknown service: $service${NC}"
            show_help
            exit 1
            ;;
    esac
    
    if [ -z "$logfile" ] && [ "$service" != "all" ]; then
        echo -e "${YELLOW}No log file found for: $service${NC}"
        echo -e "Available services: backend, frontend, ingestion, celery, mcp-docs, mcp-search, mcp-memory"
        exit 1
    fi
    
    echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   Viewing: $service logs${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
    echo -e "${BLUE}File(s): $logfile${NC}"
    echo ""
    
    if [ "$follow" = "true" ]; then
        tail -f $logfile
    else
        tail -n $lines $logfile
    fi
}

# Parse arguments
SERVICE=""
FOLLOW=false
LINES=50

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -l|--list)
            list_logs
            exit 0
            ;;
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -n)
            LINES=$2
            shift 2
            ;;
        *)
            SERVICE=$1
            shift
            ;;
    esac
done

# Show help if no service specified
if [ -z "$SERVICE" ]; then
    show_help
    exit 0
fi

# View logs
view_log "$SERVICE" "$FOLLOW" "$LINES"
