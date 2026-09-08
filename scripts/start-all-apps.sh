#!/bin/bash
# Start all applications in separate tmux panes with logging

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "=================================================="
echo -e "${BLUE}🚀 Starting All AgentMesh Applications${NC}"
echo "=================================================="
echo ""

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo -e "${YELLOW}⚠️  tmux not found. Install it for better experience:${NC}"
    echo "   macOS: brew install tmux"
    echo ""
    echo "Starting services in background instead..."
    echo ""
    
    # Start in background without tmux
    echo "📝 Logs will be written to logs/ directory"
    echo ""
    
    ./scripts/run-backend.sh > /dev/null 2>&1 &
    BACKEND_PID=$!
    echo -e "${GREEN}✅ Backend started (PID: $BACKEND_PID)${NC}"
    echo "   URL: http://localhost:8000"
    echo "   Log: logs/backend_$(date +%Y%m%d).log"
    echo ""
    
    ./scripts/run-frontend.sh > /dev/null 2>&1 &
    FRONTEND_PID=$!
    echo -e "${GREEN}✅ Frontend started (PID: $FRONTEND_PID)${NC}"
    echo "   URL: http://localhost:5173"
    echo "   Log: logs/frontend_$(date +%Y%m%d).log"
    echo ""
    
    echo "💡 To stop all services:"
    echo "   kill $BACKEND_PID $FRONTEND_PID"
    echo ""
    echo "💡 To view logs:"
    echo "   tail -f logs/backend_$(date +%Y%m%d).log"
    echo "   tail -f logs/frontend_$(date +%Y%m%d).log"
    echo ""
    
    exit 0
fi

# Create tmux session
SESSION_NAME="agentmesh"

# Check if session already exists
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Session '$SESSION_NAME' already exists${NC}"
    echo ""
    echo "Options:"
    echo "  1. Attach to existing session: tmux attach -t $SESSION_NAME"
    echo "  2. Kill existing session: tmux kill-session -t $SESSION_NAME"
    echo ""
    read -p "Kill existing session and start fresh? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        tmux kill-session -t $SESSION_NAME
        echo -e "${GREEN}✅ Killed existing session${NC}"
        echo ""
    else
        echo "Exiting..."
        exit 0
    fi
fi

echo "📝 All logs will be written to logs/ directory with date stamps"
echo ""
echo "Creating tmux session '$SESSION_NAME' with:"
echo "  - Pane 0: Backend (http://localhost:8000)"
echo "  - Pane 1: Frontend (http://localhost:5173)"
echo "  - Pane 2: Ingestion Service (http://localhost:8001)"
echo "  - Pane 3: Celery Worker"
echo ""

# Create new session with first pane (backend)
tmux new-session -d -s $SESSION_NAME -n "agentmesh"

# Send command to first pane (backend)
tmux send-keys -t $SESSION_NAME:0.0 "cd '$PROJECT_ROOT' && ./scripts/run-backend.sh" C-m

# Split window horizontally and start frontend
tmux split-window -h -t $SESSION_NAME:0
tmux send-keys -t $SESSION_NAME:0.1 "cd '$PROJECT_ROOT' && ./scripts/run-frontend.sh" C-m

# Split first pane vertically and start ingestion service
tmux select-pane -t $SESSION_NAME:0.0
tmux split-window -v -t $SESSION_NAME:0.0
tmux send-keys -t $SESSION_NAME:0.2 "cd '$PROJECT_ROOT' && ./scripts/run-ingestion.sh" C-m

# Split second pane vertically and start celery
tmux select-pane -t $SESSION_NAME:0.1
tmux split-window -v -t $SESSION_NAME:0.1
tmux send-keys -t $SESSION_NAME:0.3 "cd '$PROJECT_ROOT' && ./scripts/run-celery.sh" C-m

# Balance the panes
tmux select-layout -t $SESSION_NAME:0 tiled

echo -e "${GREEN}✅ All services started in tmux session '$SESSION_NAME'${NC}"
echo ""
echo "=================================================="
echo -e "${BLUE}📱 Service URLs:${NC}"
echo "=================================================="
echo "  Frontend:   http://localhost:5173"
echo "  Backend:    http://localhost:8000"
echo "  API Docs:   http://localhost:8000/docs"
echo "  Ingestion:  http://localhost:8001"
echo ""
echo "=================================================="
echo -e "${BLUE}📝 Log Files (auto-dated):${NC}"
echo "=================================================="
echo "  Backend:    logs/backend_$(date +%Y%m%d).log"
echo "  Frontend:   logs/frontend_$(date +%Y%m%d).log"
echo "  Ingestion:  logs/ingestion_$(date +%Y%m%d).log"
echo "  Celery:     logs/celery_$(date +%Y%m%d).log"
echo ""
echo "=================================================="
echo -e "${BLUE}🎮 Tmux Commands:${NC}"
echo "=================================================="
echo "  Attach:     tmux attach -t $SESSION_NAME"
echo "  Detach:     Ctrl+b then d"
echo "  Kill:       tmux kill-session -t $SESSION_NAME"
echo ""
echo "  Navigate panes:"
echo "    Ctrl+b then arrow keys"
echo ""
echo "  Zoom pane:"
echo "    Ctrl+b then z (toggle)"
echo ""
echo "  Scroll mode:"
echo "    Ctrl+b then [ (q to exit)"
echo ""
echo "=================================================="
echo ""
echo -e "${YELLOW}💡 Attaching to session now...${NC}"
echo "   (Press Ctrl+b then d to detach and return to terminal)"
echo ""
sleep 2

# Attach to the session
tmux attach -t $SESSION_NAME
