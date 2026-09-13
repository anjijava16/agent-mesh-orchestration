#!/bin/bash
# Run Frontend with logging

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Create logs directory
mkdir -p logs

# Generate log filename with date
LOG_FILE="logs/frontend_$(date +%Y%m%d).log"
PID_FILE="logs/frontend.pid"

echo "🎨 Starting Frontend..."
echo "📝 Logging to: $LOG_FILE"
echo "📍 Port: 5173 (dev server)"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Change to frontend directory
cd frontend

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing npm dependencies..."
    npm install
fi

# Run frontend dev server with logging
echo "✅ Frontend starting..."
npm run dev 2>&1 | tee "$PROJECT_ROOT/$LOG_FILE"
