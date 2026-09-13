# Comprehensive Logging Guide

## Overview

All AgentMesh services generate detailed logs during startup and runtime. Logs are:
- **Visible in console** during startup (real-time)
- **Saved to files** in the `logs/` directory
- **Timestamped** with date and time
- **Rotated daily** (new file per day)

## Log Directory Structure

```
logs/
├── backend_20260908_142530.log       # Backend API logs
├── frontend_20260908_142530.log      # Frontend dev server logs
├── ingestion_20260908_142530.log     # Ingestion service logs
├── celery_20260908_142530.log        # Celery worker logs
├── mcp_documents_20260908_142530.log # MCP Documents logs
├── mcp_search_20260908_142530.log    # MCP Search logs
├── mcp_memory_20260908_142530.log    # MCP Memory logs
├── backend.pid                        # Process IDs
├── ingestion.pid
├── celery.pid
├── mcp_documents.pid
├── mcp_search.pid
└── mcp_memory.pid
```

## Starting Services with Logs

### Option 1: Start All Services (Background with Saved Logs)
```bash
./start-services.sh
```
- Services run in background
- Logs saved to `logs/` directory
- **Note:** Startup logs not visible in console

### Option 2: Start with Visible Logs (Recommended)
```bash
./start-services-with-logs.sh
```
- **Shows startup logs in console** ✅
- **Saves logs to files** ✅
- Best for debugging and monitoring

### Option 3: Start Individual Services (Interactive)
```bash
# See logs in console as service runs
scripts/run-backend.sh      # Backend with logs
scripts/run-frontend.sh     # Frontend with logs
scripts/run-ingestion.sh    # Ingestion with logs
scripts/run-celery.sh       # Celery with logs
scripts/run-mcp-documents.sh # MCP Documents with logs
scripts/run-mcp-search.sh   # MCP Search with logs
scripts/run-mcp-memory.sh   # MCP Memory with logs
```
- Logs shown in console AND saved to files
- Use Ctrl+C to stop

## Viewing Logs

### Quick Log Viewer Script
```bash
# View all logs
./view-logs.sh all -f

# View specific service logs
./view-logs.sh backend -f       # Follow backend logs
./view-logs.sh celery -f        # Follow celery logs
./view-logs.sh ingestion -f     # Follow ingestion logs
./view-logs.sh mcp-docs -f      # Follow MCP documents logs

# View last N lines
./view-logs.sh backend -n 100   # Last 100 lines
./view-logs.sh celery -n 50     # Last 50 lines

# List all log files
./view-logs.sh -l

# Help
./view-logs.sh --help
```

### Manual Log Viewing

#### Watch All Today's Logs
```bash
tail -f logs/*_$(date +%Y%m%d)*.log
```

#### Watch Specific Service
```bash
# Backend
tail -f logs/backend_*.log

# Ingestion
tail -f logs/ingestion_*.log

# Celery
tail -f logs/celery_*.log

# MCP Services
tail -f logs/mcp_documents_*.log
tail -f logs/mcp_search_*.log
tail -f logs/mcp_memory_*.log
```

#### View Last N Lines
```bash
# Last 100 lines of ingestion logs
tail -n 100 logs/ingestion_*.log

# Last 50 lines of celery logs
tail -n 50 logs/celery_*.log
```

#### Search Logs
```bash
# Search for errors
grep -i "error" logs/*.log

# Search for specific text
grep "connection" logs/backend_*.log

# Search with context (3 lines before/after)
grep -C 3 "failed" logs/celery_*.log
```

## Log Contents

### What's Logged During Startup

#### Backend Service (`backend_*.log`)
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

#### Ingestion Service (`ingestion_*.log`)
```
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Connecting to PostgreSQL...
INFO:     Connecting to Redis...
INFO:     Connecting to OpenSearch...
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

#### Celery Worker (`celery_*.log`)
```
[2026-09-08 14:25:30,123: INFO/MainProcess] Connected to redis://localhost:6379//
[2026-09-08 14:25:30,234: INFO/MainProcess] mingle: searching for neighbors
[2026-09-08 14:25:31,345: INFO/MainProcess] mingle: all alone
[2026-09-08 14:25:31,456: INFO/MainProcess] celery@hostname ready.
```

#### MCP Services (`mcp_*_*.log`)
```
INFO:     Started MCP server
INFO:     Server running on 0.0.0.0:8081
INFO:     Connected to PostgreSQL
INFO:     Connected to OpenSearch
INFO:     Ready to accept requests
```

### Runtime Logs

All services log:
- **HTTP Requests**: Method, path, status code, response time
- **Database Queries**: Connection status, query execution
- **Errors**: Stack traces, error messages
- **Performance**: Response times, queue lengths
- **Health Checks**: Service health status

## Log Rotation

Logs are automatically organized by date:
- Format: `{service}_{YYYYMMDD_HHMMSS}.log`
- New file created each time services start
- Old logs preserved for debugging

### Cleaning Old Logs
```bash
# Remove logs older than 7 days
find logs/ -name "*.log" -mtime +7 -delete

# Remove logs older than 30 days
find logs/ -name "*.log" -mtime +30 -delete

# Archive logs older than 7 days
tar -czf logs_archive_$(date +%Y%m%d).tar.gz logs/*.log
find logs/ -name "*.log" -mtime +7 -delete
```

## Troubleshooting with Logs

### Service Won't Start
```bash
# Check startup errors
tail -n 100 logs/ingestion_*.log | grep -i error
tail -n 100 logs/celery_*.log | grep -i error
```

### Service Crashes
```bash
# Check for exceptions
grep -A 10 "Traceback" logs/backend_*.log
grep -A 10 "Exception" logs/celery_*.log
```

### Connection Issues
```bash
# Check database connections
grep -i "postgres\|redis\|opensearch" logs/*.log

# Check service-to-service connections
grep -i "connection\|connect\|refused" logs/*.log
```

### Performance Issues
```bash
# Check response times
grep "GET\|POST\|PUT\|DELETE" logs/backend_*.log | grep -E "[0-9]+ms"

# Check queue lengths
grep "queue" logs/celery_*.log
```

## Log Levels

Services support different log levels:

```bash
# Development (verbose)
export LOG_LEVEL=DEBUG

# Production (standard)
export LOG_LEVEL=INFO

# Critical only
export LOG_LEVEL=ERROR
```

Update in `.env` file:
```bash
LOG_LEVEL=INFO
LOG_FORMAT=console  # or 'json' for structured logging
```

## Real-Time Monitoring

### Monitor All Services
```bash
# Terminal 1: Watch all logs
tail -f logs/*_$(date +%Y%m%d)*.log

# Terminal 2: Watch errors only
tail -f logs/*_$(date +%Y%m%d)*.log | grep -i "error\|exception\|fail"
```

### Monitor Specific Service
```bash
# Watch backend with color highlighting
tail -f logs/backend_*.log | grep --color=always -E 'ERROR|WARNING|INFO'

# Watch celery tasks
tail -f logs/celery_*.log | grep -E 'Task.*succeeded|Task.*failed'
```

## Log Aggregation

For production, consider log aggregation tools:
- **ELK Stack**: Elasticsearch, Logstash, Kibana
- **Grafana Loki**: Lightweight log aggregation
- **CloudWatch**: AWS log management
- **Datadog**: Application monitoring

## Best Practices

1. **Always Check Logs First** when debugging
2. **Use Log Viewer Script** for convenience
3. **Monitor Startup Logs** to catch early issues
4. **Search Logs** for specific errors
5. **Archive Old Logs** to save disk space
6. **Set Appropriate Log Levels** for environment
7. **Use Structured Logging** (JSON) in production

## Quick Reference

| Command | Purpose |
|---------|---------|
| `./start-services-with-logs.sh` | Start all with visible logs |
| `./view-logs.sh all -f` | Watch all logs |
| `./view-logs.sh backend -f` | Watch backend logs |
| `./view-logs.sh -l` | List all log files |
| `tail -f logs/*.log` | Watch all logs manually |
| `grep -i error logs/*.log` | Find errors |
| `ls -lh logs/` | Check log file sizes |

## Service-Specific Logs

### Backend (`logs/backend_*.log`)
- API requests and responses
- Database queries
- Authentication events
- LiteLLM proxy calls
- Error traces

### Ingestion (`logs/ingestion_*.log`)
- Document uploads
- File processing
- Embedding generation
- OpenSearch indexing
- Upload status

### Celery (`logs/celery_*.log`)
- Task execution
- Worker status
- Queue status
- Task success/failure
- Retry attempts

### MCP Services (`logs/mcp_*_*.log`)
- MCP protocol messages
- Tool executions
- Database operations
- Search queries
- Memory operations

## Example Log Analysis

### Find Failed Tasks
```bash
grep "failed" logs/celery_*.log | tail -20
```

### Count HTTP Status Codes
```bash
grep "HTTP" logs/backend_*.log | grep -oE "[0-9]{3}" | sort | uniq -c
```

### Find Slow Requests (>1000ms)
```bash
grep -E "[0-9]{4,}ms" logs/backend_*.log
```

### Check Service Health
```bash
grep "health" logs/*.log | tail -20
```

---

**Remember:** Logs are your best friend for debugging! Always check logs first when troubleshooting issues.
