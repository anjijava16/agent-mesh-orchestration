#!/bin/bash
# Run Backend service with logging

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Create logs directory
mkdir -p logs

# Generate log filename with date
LOG_FILE="logs/backend_$(date +%Y%m%d).log"
PID_FILE="logs/backend.pid"

echo "🚀 Starting Backend Service..."
echo "📝 Logging to: $LOG_FILE"
echo "📍 Port: 8000"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Change to backend directory
cd backend

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
export LITELLM_BASE_URL=http://localhost:4000

# Run backend with logging (both console and file)
echo "✅ Backend starting..."
cd "$PROJECT_ROOT/backend"

uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info \
    --reload \
    2>&1 | tee "$PROJECT_ROOT/$LOG_FILE"
