# How to Check if Celery is Working

## Quick Check Commands

### 1. Check if Celery Worker is Running

```bash
# Check process
ps aux | grep "celery.*app.worker.celery_app" | grep -v grep

# Or check PID file
cat logs/celery.pid
ps -p $(cat logs/celery.pid) 2>/dev/null && echo "Running" || echo "Not running"
```

### 2. Ping the Celery Worker

```bash
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate

# Ping the worker
celery -A app.worker.celery_app inspect ping

# Expected output:
# -> celery@hostname: OK
#     pong
# 1 node online.
```

### 3. Check Active Tasks

```bash
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate

# See active tasks
celery -A app.worker.celery_app inspect active

# See registered tasks
celery -A app.worker.celery_app inspect registered

# Worker statistics
celery -A app.worker.celery_app inspect stats
```

### 4. Check Celery Logs

```bash
# View real-time logs
tail -f logs/celery_*.log

# Check for errors
grep -i "error\|exception\|traceback" logs/celery_*.log

# View last 50 lines
tail -50 logs/celery_*.log
```

### 5. Check Redis Connection

Celery uses Redis as a message broker:

```bash
# Test Redis connection
docker exec -it agentmesh-redis redis-cli ping
# Should return: PONG

# Check Redis info
docker exec -it agentmesh-redis redis-cli info | grep connected_clients

# Check Celery queues in Redis
docker exec -it agentmesh-redis redis-cli -n 1 keys "*"
```

## Common Celery Issues & Solutions

### Issue 1: ModuleNotFoundError: No module named 'psycopg'

**Symptoms:**
```
ModuleNotFoundError: No module named 'psycopg'
```

**Solution:**
```bash
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate
pip install 'psycopg[binary]'
```

**This has been fixed** in requirements.txt.

### Issue 2: Cannot Connect to Redis

**Symptoms:**
```
Error 8 connecting to redis:6379. nodename nor servname provided, or not known.
```

**Solution:**
For local development, ensure environment variables are set:
```bash
export REDIS_HOST=localhost
export POSTGRES_HOST=localhost
export OPENSEARCH_HOST=localhost
```

**This is automatically handled** by `start-services.sh`.

### Issue 3: Worker Not Responding

**Restart Celery:**
```bash
# Stop all services
./stop-services.sh

# Start again
./start-services.sh

# Or restart just Celery
pkill -9 -f "celery.*app.worker.celery_app"
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate
export REDIS_HOST=localhost POSTGRES_HOST=localhost OPENSEARCH_HOST=localhost
nohup celery -A app.worker.celery_app worker --loglevel=INFO --concurrency=2 -Q ingest,default > logs/celery_$(date +%Y%m%d).log 2>&1 &
```

## Testing Celery with a Real Task

### 1. Submit a Test Ingestion Task

```bash
# Submit an ingestion task via API
curl -X POST http://localhost:8001/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "test123",
    "filename": "test.pdf",
    "user_id": "user1",
    "vector_backend": "opensearch",
    "chunk_size": 512,
    "chunk_overlap": 50
  }'

# Response will include task_id:
# {"task_id":"abc-123-def","status":"queued","message":"..."}
```

### 2. Check Task Status

```bash
# Replace TASK_ID with actual task ID from above
curl http://localhost:8001/api/v1/tasks/TASK_ID | python3 -m json.tool
```

### 3. Monitor in Real-Time

```bash
# In one terminal - watch logs
tail -f logs/celery_*.log

# In another terminal - submit task (see above)

# You should see:
# - Task received
# - Task executing
# - Task completed or failed
```

## Celery Health Check Script

Create a quick health check:

```bash
#!/bin/bash
cd agentservices/ingestion/ingestion-service
source .venv/bin/activate

echo "Checking Celery Worker..."
if celery -A app.worker.celery_app inspect ping -t 3 2>&1 | grep -q "pong"; then
    echo "✅ Celery Worker is healthy"
    
    # Show registered tasks
    echo -e "\nRegistered Tasks:"
    celery -A app.worker.celery_app inspect registered | grep -A 10 "celery@"
    
    # Show active tasks
    echo -e "\nActive Tasks:"
    celery -A app.worker.celery_app inspect active | grep -A 5 "celery@" | head -10
    
    exit 0
else
    echo "❌ Celery Worker is not responding"
    echo "Check logs: tail -f logs/celery_*.log"
    exit 1
fi
```

Save as `check-celery.sh` and run:
```bash
chmod +x check-celery.sh
./check-celery.sh
```

## Monitoring with Flower (Optional)

Flower is a web UI for monitoring Celery:

```bash
# Start Flower (included in docker-compose.yml)
docker compose --profile tools up -d flower

# Access at: http://localhost:5555
```

In Flower you can see:
- Active workers
- Task history
- Task stats
- Worker utilization
- Real-time monitoring

## Expected Celery Output (Healthy)

When Celery is working correctly:

### Ping Test:
```
$ celery -A app.worker.celery_app inspect ping
-> celery@hostname: OK
    pong
1 node online.
```

### Registered Tasks:
```
$ celery -A app.worker.celery_app inspect registered
-> celery@hostname: OK
    * app.worker.tasks.ingest_document
    * app.worker.tasks.purge_document
```

### Stats:
```
$ celery -A app.worker.celery_app inspect stats
-> celery@hostname: OK
    - total: {
        'app.worker.tasks.ingest_document': 5,
        'app.worker.tasks.purge_document': 2
    }
```

## Troubleshooting Checklist

- [ ] Redis is running: `docker ps | grep redis`
- [ ] PostgreSQL is running: `docker ps | grep postgres`
- [ ] Worker process exists: `ps aux | grep celery`
- [ ] No errors in logs: `tail -50 logs/celery_*.log`
- [ ] Redis connection works: `docker exec agentmesh-redis redis-cli ping`
- [ ] Ping succeeds: `celery -A app.worker.celery_app inspect ping`
- [ ] Tasks registered: `celery -A app.worker.celery_app inspect registered`
- [ ] Environment variables set: `echo $REDIS_HOST` (should be "localhost" for local dev)

## Summary

**To check if Celery is working:**

1. **Quick check:**
   ```bash
   ./check-services.sh
   # Look for: ✓ Celery Worker: Responding
   ```

2. **Detailed check:**
   ```bash
   cd agentservices/ingestion/ingestion-service
   source .venv/bin/activate
   celery -A app.worker.celery_app inspect ping
   ```

3. **Check logs:**
   ```bash
   tail -f logs/celery_*.log
   ```

4. **Test with real task:**
   ```bash
   # Submit task via ingestion API
   curl -X POST http://localhost:8001/api/v1/ingest \
     -H "Content-Type: application/json" \
     -d '{"file_id":"test","filename":"test.pdf","user_id":"user1"}'
   
   # Watch logs
   tail -f logs/celery_*.log
   ```

**All issues resolved!** ✅ Celery is now properly configured and working.
