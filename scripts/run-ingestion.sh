#!/bin/bash
# Run Ingestion service with logging

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Create logs directory
mkdir -p logs

# Generate log filename with date
LOG_FILE="logs/ingestion_$(date +%Y%m%d).log"
PID_FILE="logs/ingestion.pid"

echo "📥 Starting Ingestion Service..."
echo "📝 Logging to: $LOG_FILE"
echo "📍 Port: 8001"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Change to ingestion service directory
cd agentservices/ingestion/ingestion-service

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
export REDIS_HOST=localhost
export OPENSEARCH_HOST=localhost

# Run ingestion service with logging (both console and file)
echo "✅ Ingestion service starting..."
cd "$PROJECT_ROOT/agentservices/ingestion/ingestion-service"

uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8001 \
    --log-level info \
    --reload \
    2>&1 | tee "$PROJECT_ROOT/$LOG_FILE"
