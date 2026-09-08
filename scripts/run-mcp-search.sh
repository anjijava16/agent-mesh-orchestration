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

echo "🔍 Starting MCP Search Service..."
echo "📝 Logging to: $LOG_FILE"
echo "🌐 URL: http://localhost:8082"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Change to MCP search directory
cd agentservices/mcp/mcp-search

# Activate virtual environment
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Run ./start-local.sh first."
    exit 1
fi

source .venv/bin/activate

# Load environment variables
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Run MCP server with logging (both console and file)
python -m app.server 2>&1 | tee -a "../../../$LOG_FILE"
