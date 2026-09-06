# AgentMesh - Installation & CLI Reference

## Quick Start

```bash
# Build and start all services
docker compose up -d --build

# Run database migrations
docker compose exec backend alembic upgrade head

# Open the app
open http://localhost:8080
```

## Check Service Status

```bash
# All services
docker compose ps

# Logs (follow mode)
docker compose logs -f backend

# Logs for a specific service
docker compose logs --tail 50 phoenix
docker compose logs --tail 50 neo4j
```

---

## CLI Access to Each Service

### PostgreSQL

```bash
# Connect to psql shell
docker compose exec postgres psql -U agentmesh -d agentmesh

# Once inside psql:
\dt                              -- list all tables
\d+ conversations                -- describe a table
SELECT count(*) FROM conversations;
SELECT id, title, framework, created_at FROM conversations ORDER BY created_at DESC LIMIT 10;
SELECT id, status, framework, tokens FROM agent_runs ORDER BY created_at DESC LIMIT 10;
SELECT id, role, agent_name, framework FROM messages ORDER BY created_at DESC LIMIT 10;
\q                               -- quit

# One-liner from host (no interactive shell)
docker compose exec postgres psql -U agentmesh -d agentmesh -c "SELECT count(*) FROM conversations;"
docker compose exec postgres psql -U agentmesh -d agentmesh -c "\dt"
```

### OpenSearch

```bash
# Cluster health
docker compose exec opensearch curl -s 'http://localhost:9200/_cluster/health' | python3 -m json.tool

# List all indices
docker compose exec opensearch curl -s 'http://localhost:9200/_cat/indices?v'

# Count documents in the documents index
docker compose exec opensearch curl -s 'http://localhost:9200/agentmesh-documents/_count' | python3 -m json.tool

# Search for documents (first 5)
docker compose exec opensearch curl -s 'http://localhost:9200/agentmesh-documents/_search?size=5&_source_excludes=embedding' | python3 -m json.tool

# List all unique filenames in the corpus
docker compose exec opensearch curl -s -X POST 'http://localhost:9200/agentmesh-documents/_search' \
  -H 'Content-Type: application/json' \
  -d '{"size":0,"aggs":{"files":{"terms":{"field":"filename","size":100}}}}' | python3 -m json.tool

# Long-term memory index
docker compose exec opensearch curl -s 'http://localhost:9200/agentmesh-longterm-memory/_count' | python3 -m json.tool

# Or from host directly (port 9200 is exposed)
curl -s 'http://localhost:9200/_cluster/health' | python3 -m json.tool
curl -s 'http://localhost:9200/_cat/indices?v'
```

### Redis

```bash
# Connect to redis-cli
docker compose exec redis redis-cli

# Once inside redis-cli:
INFO keyspace                    -- show databases and key counts
KEYS *                           -- list all keys (careful in production)
DBSIZE                           -- count keys in current DB
TYPE <key>                       -- check key type
GET <key>                        -- get a string key
TTL <key>                        -- check expiry
QUIT                             -- exit

# Celery broker DB (db 1)
docker compose exec redis redis-cli -n 1
KEYS *                           -- see queued tasks

# Celery results DB (db 2)
docker compose exec redis redis-cli -n 2
KEYS *                           -- see task results

# One-liner from host
docker compose exec redis redis-cli DBSIZE
docker compose exec redis redis-cli INFO keyspace
```

### MinIO (S3-compatible Object Storage)

```bash
# List all buckets
docker compose exec minio mc ls local/

# List files in the uploads bucket
docker compose exec minio mc ls local/agentmesh-uploads/

# List files recursively with sizes
docker compose exec minio mc ls --recursive --summarize local/agentmesh-uploads/

# Get bucket stats
docker compose exec minio mc stat local/agentmesh-uploads/

# Download a file to inspect
docker compose exec minio mc cat local/agentmesh-uploads/<path-to-file>

# Or use the MinIO Console (web UI)
# http://localhost:9001  (login: minioadmin / minioadmin)
```

### Neo4j (Graph Database)

```bash
# Connect to cypher-shell
docker compose exec neo4j cypher-shell -u neo4j -p agentmesh2026

# Once inside cypher-shell:
SHOW DATABASES;
MATCH (n) RETURN labels(n) AS label, count(*) AS count;    // count nodes by label
MATCH (n) RETURN n LIMIT 10;                                // first 10 nodes
MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS count;  // count relationships
MATCH (n) DETACH DELETE n;                                   // clear all data (careful!)
:exit                                                        // quit

# One-liner from host
docker compose exec neo4j cypher-shell -u neo4j -p agentmesh2026 "MATCH (n) RETURN count(n);"

# Or use the Neo4j Browser (web UI)
# http://localhost:7474  (login: neo4j / agentmesh2026)
```

### Arize Phoenix (AI Observability)

```bash
# Check Phoenix data files on your Mac
ls -la infra/phoenix/data/

```
(base) welcome@jaisairams-Laptop agentmesh % ls -la infra/phoenix/data/
total 2664
drwxr-xr-x@ 8 welcome  staff     256 Sep  5 22:27 .
drwxr-xr-x@ 3 welcome  staff      96 Sep  5 22:27 ..
drwxr-xr-x  2 welcome  staff      64 Sep  5 22:27 inferences
-rw-r--r--  1 welcome  staff  987136 Sep  5 22:27 phoenix.db
-rw-r--r--  1 welcome  staff   32768 Sep  5 22:27 phoenix.db-shm
-rw-r--r--@ 1 welcome  staff  280192 Sep  5 22:27 phoenix.db-wal
drwxr-xr-x  2 welcome  staff      64 Sep  5 22:27 trace_datasets
drwxr-xr-x  2 welcome  staff      64 Sep  5 22:27 wasm
(base) welcome@jaisairams-Laptop agentmesh % ls -ltr infra/
total 0
drwxr-xr-x@ 3 welcome  staff   96 Sep  4 11:08 postgres
drwxr-xr-x@ 4 welcome  staff  128 Sep  4 11:08 opensearch
drwxr-xr-x@ 3 welcome  staff   96 Sep  4 11:08 nginx
drwxr-xr-x@ 3 welcome  staff   96 Sep  5 22:27 phoenix
(base) welcome@jaisairams-Laptop agentmesh %    

```

# The SQLite DB file
ls -lh infra/phoenix/data/phoenix.db

# Query the Phoenix DB directly (if sqlite3 is installed)
sqlite3 infra/phoenix/data/phoenix.db ".tables"
sqlite3 infra/phoenix/data/phoenix.db "SELECT count(*) FROM spans;"

# Or use the Phoenix Web UI
# http://localhost:6006
```

---

## Web UIs

| Service              | URL                     | Credentials                |
|----------------------|-------------------------|----------------------------|
| AgentMesh App        | http://localhost:8080    | -                          |
| AgentMesh API        | http://localhost:8000    | -                          |
| Arize Phoenix        | http://localhost:6006    | -                          |
| Neo4j Browser        | http://localhost:7474    | neo4j / agentmesh2026      |
| MinIO Console        | http://localhost:9001    | minioadmin / minioadmin    |
| OpenSearch Dashboards| http://localhost:5601    | (tools profile only)       |
| Flower (Celery)      | http://localhost:5555    | (tools profile only)       |

## Useful Docker Commands

```bash
# Restart a single service
docker compose restart backend

# Rebuild and restart backend only
docker compose build backend && docker compose up -d backend

# Full rebuild (no cache)
docker compose build --no-cache backend

# Stop everything
docker compose down

# Stop everything and remove volumes (DELETES ALL DATA)
docker compose down -v

# Shell into the backend container
docker compose exec backend bash

# Run a Python command in the backend
docker compose exec backend python -c "from app.config import settings; print(settings.agent.framework)"

# Check framework list
docker compose exec backend python -c "from app.agents.registry import available_frameworks; [print(f'{f[\"id\"]}: {f[\"installed\"]}') for f in available_frameworks()]"
```

## Environment Variables

Key settings in `.env`:

```bash
# Agent framework: langgraph, google_adk, google_adk_workflow, deepagents, claude_agent_sdk, ms_agent_framework, strands_agents
AGENT_FRAMEWORK=langgraph

# Model provider: openai, anthropic, google
AGENT_PROVIDER=anthropic
AGENT_MODEL=claude-sonnet-4-6

# Search provider: auto, tavily, duckduckgo
SEARCH_PROVIDER=auto

# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=DEBUG
```
