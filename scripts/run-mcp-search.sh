#!/bin/bash
# Run MCP Search service with logging

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Create logs directory
mkdir -p logs

# Generate log filename with date
LOG_FILE="logs/mcp_search_$(date +%Y%m%d).log"
PID_FILE="logs/mcp_search.pid"

echo "🔍 Starting MCP Search Service..."
echo "📝 Logging to: $LOG_FILE"
echo "📍 Port: 8082"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Change to MCP search directory
cd agentservices/mcp/mcp-search

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
export OPENSEARCH_HOST=localhost
export MCP_SERVER_PORT=8082
export MCP_SERVER_HOST=0.0.0.0

# Run MCP service with logging
echo "✅ MCP Search service starting..."
cd "$PROJECT_ROOT/agentservices/mcp/mcp-search"

python -m app.server 2>&1 | tee "$PROJECT_ROOT/$LOG_FILE"
