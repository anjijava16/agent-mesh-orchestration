#!/bin/bash
# Run Celery worker with logging

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Create logs directory
mkdir -p logs

# Generate log filename with date
LOG_FILE="logs/celery_$(date +%Y%m%d).log"

echo "⚙️  Starting Celery Worker..."
echo "📝 Logging to: $LOG_FILE"
echo "📋 Queues: ingest, default"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Change to ingestion service directory
cd agentservices/ingestion/ingestion-service

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

# Run celery with logging (both console and file)
celery -A app.worker.celery_app worker \
    --loglevel=INFO \
    --concurrency=2 \
    -Q ingest,default \
    2>&1 | tee -a "../../../$LOG_FILE"
