# Logging Guide - AgentMesh

## Overview

All applications write logs to the `logs/` directory with date-stamped filenames for easy tracking and rotation.

## Log File Format

```
logs/<service>_YYYYMMDD.log
```

### Examples:
- `logs/backend_20260908.log` - Backend API logs for September 8, 2026
- `logs/frontend_20260908.log` - Frontend logs for September 8, 2026
- `logs/mcp_documents_20260908.log` - MCP Documents service logs

## Available Run Scripts

All scripts automatically create logs with date stamps:

| Script | Service | Port | Log File |
|--------|---------|------|----------|
| `./run-backend.sh` | Backend API | 8000 | `logs/backend_YYYYMMDD.log` |
| `./run-frontend.sh` | Frontend UI | 5173 | `logs/frontend_YYYYMMDD.log` |
| `./run-ingestion.sh` | Ingestion Service | 8001 | `logs/ingestion_YYYYMMDD.log` |
| `./run-celery.sh` | Celery Worker | - | `logs/celery_YYYYMMDD.log` |
| `./run-mcp-documents.sh` | MCP Documents | 8081 | `logs/mcp_documents_YYYYMMDD.log` |
| `./run-mcp-search.sh` | MCP Search | 8082 | `logs/mcp_search_YYYYMMDD.log` |
| `./run-mcp-memory.sh` | MCP Memory | 8083 | `logs/mcp_memory_YYYYMMDD.log` |

---

## Quick Start

### Option 1: Start All Services with Tmux (Recommended)

```bash
./start-all-apps.sh
```

**This will:**
1. Start all services in separate tmux panes
2. Log everything to dated files
3. Show all services in one terminal window

**Tmux Controls:**
- **Detach:** `Ctrl+b` then `d`
- **Reattach:** `tmux attach -t agentmesh`
- **Kill session:** `tmux kill-session -t agentmesh`
- **Navigate panes:** `Ctrl+b` then arrow keys
- **Zoom pane:** `Ctrl+b` then `z`

### Option 2: Start Services Individually

```bash
# Terminal 1 - Backend
./run-backend.sh

# Terminal 2 - Frontend
./run-frontend.sh

# Terminal 3 - Ingestion (optional)
./run-ingestion.sh

# Terminal 4 - Celery (optional)
./run-celery.sh
```

---

## Viewing Logs

### Real-time Tail

```bash
# Watch backend logs
tail -f logs/backend_$(date +%Y%m%d).log

# Watch all logs
tail -f logs/*.log

# Watch specific service
tail -f logs/frontend_$(date +%Y%m%d).log
```

### Search Logs

```bash
# Search for errors in today's backend log
grep -i error logs/backend_$(date +%Y%m%d).log

# Search across all logs
grep -i "connection refused" logs/*.log

# Count errors per service
for log in logs/*_$(date +%Y%m%d).log; do
    echo "$log: $(grep -c -i error $log 2>/dev/null || echo 0) errors"
done
```

### View Recent Logs

```bash
# Last 50 lines
tail -n 50 logs/backend_$(date +%Y%m%d).log

# Last 100 lines from all services
tail -n 100 logs/*_$(date +%Y%m%d).log
```

---

## Log Rotation

Logs are automatically organized by date. Old logs are kept for reference.

### Manual Cleanup

```bash
# Remove logs older than 7 days
find logs/ -name "*.log" -mtime +7 -delete

# Archive old logs
tar -czf logs_archive_$(date +%Y%m).tar.gz logs/*.log
rm logs/*.log
```

### Automatic Cleanup Script

Create `scripts/cleanup-logs.sh`:

```bash
#!/bin/bash
# Keep only last 30 days of logs

find logs/ -name "*.log" -mtime +30 -delete
echo "✅ Logs older than 30 days removed"
```

---

## Log Format

### Backend & Ingestion Services

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     127.0.0.1:54321 - "GET /api/v1/health HTTP/1.1" 200 OK
```

### Frontend

```
  VITE v5.0.0  ready in 1234 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
  ➜  press h + enter to show help
```

### Celery Worker

```
[2026-09-08 10:15:30,123: INFO/MainProcess] Connected to redis://localhost:6379//
[2026-09-08 10:15:30,456: INFO/MainProcess] celery@hostname ready.
[2026-09-08 10:15:35,789: INFO/MainProcess] Task ingest_file[123] received
[2026-09-08 10:15:40,012: INFO/ForkPoolWorker-1] Task ingest_file[123] succeeded
```

---

## Troubleshooting

### No Logs Being Created

**Problem:** `logs/` directory doesn't exist

**Solution:**
```bash
mkdir -p logs
./run-backend.sh
```

### Can't Write to Log File

**Problem:** Permission denied

**Solution:**
```bash
chmod 755 logs
chmod 644 logs/*.log
```

### Logs Growing Too Large

**Problem:** Log files consuming disk space

**Solution:**
```bash
# Check log sizes
du -sh logs/*

# Archive and compress
tar -czf logs/archive_$(date +%Y%m%d).tar.gz logs/*.log
rm logs/*.log
```

### Log File Not Updating

**Problem:** Old date in filename

**Solution:** The date is set when the script starts. Restart the service to get a new dated log file.

---

## Advanced Usage

### Log to Both File and Console

All scripts use `tee` which writes to both:
```bash
uvicorn app.main:app --reload 2>&1 | tee -a logs/backend_$(date +%Y%m%d).log
```

### Custom Log Location

Edit the run script to change log location:
```bash
# In scripts/run-backend.sh
LOG_FILE="custom_logs/my_backend.log"
```

### Add Timestamps to Console Output

```bash
# In run script, add:
ts() { while read line; do echo "$(date '+%Y-%m-%d %H:%M:%S') $line"; done; }
uvicorn app.main:app --reload 2>&1 | ts | tee -a logs/backend_$(date +%Y%m%d).log
```

### Separate Error Logs

```bash
# Redirect stderr to separate file
uvicorn app.main:app --reload \
    > logs/backend_$(date +%Y%m%d).log \
    2> logs/backend_errors_$(date +%Y%m%d).log
```

---

## Log Analysis

### Count Requests by Endpoint

```bash
grep "GET\|POST\|PUT\|DELETE" logs/backend_$(date +%Y%m%d).log | \
    awk '{print $5}' | sort | uniq -c | sort -rn
```

### Find Slow Requests

```bash
# Requests taking > 1 second
grep "completed in" logs/backend_$(date +%Y%m%d).log | \
    awk '$NF > 1000' 
```

### Error Summary

```bash
# Count errors by type
grep -i error logs/*_$(date +%Y%m%d).log | \
    awk -F: '{print $NF}' | sort | uniq -c | sort -rn
```

### Active Users/IPs

```bash
# Extract IPs from backend logs
grep "GET\|POST" logs/backend_$(date +%Y%m%d).log | \
    awk '{print $1}' | sort | uniq -c | sort -rn
```

---

## Integration with Monitoring Tools

### Send Logs to External Service

```bash
# Example: Send to Logtail/Papertrail
tail -f logs/backend_$(date +%Y%m%d).log | \
    nc logs.papertrailapp.com 12345
```

### JSON Structured Logging

Modify backend to output JSON:
```python
import logging
import json

logging.basicConfig(
    format='{"time":"%(asctime)s", "level":"%(levelname)s", "message":"%(message)s"}',
    level=logging.INFO
)
```

---

## Best Practices

### 1. Regular Cleanup
```bash
# Add to crontab
0 0 * * 0 find /path/to/logs -name "*.log" -mtime +30 -delete
```

### 2. Monitor Disk Space
```bash
# Alert if logs > 1GB
LOG_SIZE=$(du -sb logs | awk '{print $1}')
if [ $LOG_SIZE -gt 1073741824 ]; then
    echo "⚠️  Logs exceed 1GB"
fi
```

### 3. Structured Naming
Always use: `<service>_YYYYMMDD.log` format

### 4. Git Ignore
```bash
# Add to .gitignore
logs/
*.log
```

### 5. Backup Important Logs
```bash
# Weekly backup
tar -czf logs_backup_$(date +%Y%W).tar.gz logs/
mv logs_backup_*.tar.gz backups/
```

---

## Quick Commands Reference

```bash
# View today's logs
tail -f logs/*_$(date +%Y%m%d).log

# Search all logs for error
grep -r "error" logs/

# Count lines per log
wc -l logs/*.log

# Show log file sizes
ls -lh logs/

# Archive last month's logs
tar -czf logs_$(date -v-1m +%Y%m).tar.gz logs/*_$(date -v-1m +%Y%m)*.log

# Remove logs older than 7 days
find logs/ -mtime +7 -delete
```

---

## Summary

| Task | Command |
|------|---------|
| Start all services | `./start-all-apps.sh` |
| View backend logs | `tail -f logs/backend_$(date +%Y%m%d).log` |
| View all logs | `tail -f logs/*.log` |
| Search for errors | `grep -i error logs/*.log` |
| Archive old logs | `tar -czf archive.tar.gz logs/*.log` |
| Delete old logs | `find logs/ -mtime +30 -delete` |

---

**Location:** All logs in `logs/` directory  
**Format:** `<service>_YYYYMMDD.log`  
**Rotation:** Automatic by date, manual cleanup recommended  
**Git:** logs/ directory is ignored
