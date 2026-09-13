#!/bin/bash
# Run MCP Memory service with logging

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Create logs directory
mkdir -p logs

# Generate log filename with date
LOG_FILE="logs/mcp_memory_$(date +%Y%m%d).log"
PID_FILE="logs/mcp_memory.pid"

echo "🧠 Starting MCP Memory Service..."
echo "📝 Logging to: $LOG_FILE"
echo "📍 Port: 8083"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Change to MCP memory directory
cd agentservices/mcp/mcp-memory

# Activate virtual environment
if [ ! -d ".venv" ]; then
    echo "⚙️  Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Install/upgrade dependencies
echo "📦 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Load environment variables
cd "$PROJECT_ROOT"
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Override for local development
export POSTGRES_HOST=localhost
export OPENSEARCH_HOST=localhost
export MCP_SERVER_PORT=8083
export MCP_SERVER_HOST=0.0.0.0

# Run MCP service with logging
echo "✅ MCP Memory service starting..."
cd "$PROJECT_ROOT/agentservices/mcp/mcp-memory"

python -m app.server 2>&1 | tee "$PROJECT_ROOT/$LOG_FILE"
