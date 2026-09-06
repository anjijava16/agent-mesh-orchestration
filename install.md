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


(base) welcome@jaisairams-Laptop agentmesh % docker compose exec opensearch curl -s 'http://localhost:9200/_cat/indices?v'
health status index                     uuid                   pri rep docs.count docs.deleted store.size pri.store.size
green  open   .opensearch-observability WHLj3LWBSZSP0AlX91bNCw   1   0          0            0       208b           208b
green  open   .plugins-ml-config        UlFpE7XIQmWhEufQaOrvRw   1   0          1            0      3.9kb          3.9kb
green  open   agentmesh-documents       D5vYHqLCRL2kYwYzDdKciQ   2   0          0            0       462b           462b
green  open   agentmesh-longterm-memory ISn3r6vURuazF1HxsknDlw   1   0          0            0       208b           208b
(base) welcome@jaisairams-Laptop agentmesh % 



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

Phoenix uses the same Postgres instance (database: `phoenix`).

```bash
# Connect to the Phoenix database
docker compose exec postgres psql -U agentmesh -d phoenix

# Once inside psql:
\dt                              -- list all Phoenix tables
\d+ spans                        -- describe the spans table
SELECT count(*) FROM projects;
SELECT count(*) FROM spans;
SELECT count(*) FROM traces;

# Recent traces
SELECT id, trace_id, name, status_code, latency_ms 
FROM spans ORDER BY created_at DESC LIMIT 10;

# Projects
SELECT id, name, created_at FROM projects;

# Datasets and experiments
SELECT id, name, created_at FROM datasets;
SELECT id, name, created_at FROM experiments;
\q                               -- quit

# One-liners from host
docker compose exec postgres psql -U agentmesh -d phoenix -c "\dt"
docker compose exec postgres psql -U agentmesh -d phoenix -c "SELECT count(*) FROM spans;"
docker compose exec postgres psql -U agentmesh -d phoenix -c "SELECT count(*) FROM traces;"
docker compose exec postgres psql -U agentmesh -d phoenix -c "SELECT name, count(*) FROM spans GROUP BY name ORDER BY count DESC LIMIT 10;"

# List all databases in Postgres (agentmesh + phoenix)
docker compose exec postgres psql -U agentmesh -d agentmesh -c "\l"

# Or use the Phoenix Web UI
# http://localhost:6006
```

### Opik (Comet AI Observability)

Opik uses its own MySQL + ClickHouse stack.

```bash
# Check all Opik services status
docker compose ps --filter "name=opik"

# Opik backend health
curl -s 'http://localhost:8083/health-check'

# --- Opik REST API (via frontend proxy) ---

# List projects
curl -s 'http://localhost:5174/api/v1/private/projects' | python3 -m json.tool

# List traces for a project
curl -s 'http://localhost:5174/api/v1/private/traces?project_name=Default%20Project&size=10' | python3 -m json.tool

# List spans
curl -s 'http://localhost:5174/api/v1/private/spans?project_name=Default%20Project&size=10' | python3 -m json.tool

# List datasets
curl -s 'http://localhost:5174/api/v1/private/datasets' | python3 -m json.tool

# List experiments
curl -s 'http://localhost:5174/api/v1/private/experiments' | python3 -m json.tool

# --- Opik OpenAPI Spec ---
# Download the full API spec
curl -s 'http://localhost:3003/openapi.yaml' > opik-openapi.yaml

# --- Opik MySQL (state DB) ---
docker compose exec opik-mysql mysql -u opik -popik opik

# Once inside mysql:
# SHOW TABLES;
# SELECT count(*) FROM projects;
# SELECT count(*) FROM traces;
# exit;

# One-liner from host
docker compose exec opik-mysql mysql -u opik -popik opik -e "SHOW TABLES;"

# --- Opik ClickHouse (analytics DB) ---
docker compose exec opik-clickhouse clickhouse-client --user opik --password opik --database opik

# Once inside clickhouse-client:
# SHOW TABLES;
# SELECT count() FROM traces;
# SELECT count() FROM spans;
# SELECT project_name, count() FROM traces GROUP BY project_name;
# exit;

# One-liner from host
docker compose exec opik-clickhouse clickhouse-client --user opik --password opik --database opik -q "SHOW TABLES"

# --- Opik logs ---
docker compose logs opik-backend --tail 20
docker compose logs opik-frontend --tail 10

# --- Restart Opik stack ---
docker compose restart opik-backend opik-frontend

# --- Full Opik stack restart (including infra) ---
docker compose stop opik-frontend opik-backend opik-clickhouse opik-zookeeper opik-mysql opik-redis opik-minio
docker compose up -d opik-mysql opik-redis opik-zookeeper opik-clickhouse opik-minio
# Wait 30s for infra, then:
docker compose up -d opik-backend
# Wait 60-120s for backend migrations, then:
docker compose up -d opik-frontend

# Or use the Opik Web UI
# http://localhost:5174
```

---

## Web UIs

| Service              | URL                     | Credentials                |
|----------------------|-------------------------|----------------------------|
| AgentMesh App        | http://localhost:8080    | -                          |
| AgentMesh API Docs   | http://localhost:8000/docs | -                        |
| Arize Phoenix        | http://localhost:6006    | -                          |
| Opik UI              | http://localhost:5174    | -                          |
| Opik API             | http://localhost:8083    | -                          |
| Opik OpenAPI Spec    | http://localhost:3003    | -                          |
| Neo4j Browser        | http://localhost:7474    | neo4j / agentmesh2026      |
| MinIO Console        | http://localhost:9001    | minioadmin / minioadmin    |
| OpenSearch Dashboards| http://localhost:5601    | -                          |
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
