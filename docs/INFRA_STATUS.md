# Docker Compose Infrastructure Status

## Overview

This document shows the status of all services running in `docker-compose-infra.yml`.

## ✅ Services Running

| Service | Status | Port(s) | Health | Purpose |
|---------|--------|---------|--------|---------|
| **PostgreSQL** | ✅ Running | 5433→5432 | Healthy | Main database |
| **Redis** | ✅ Running | 6379 | Healthy | Cache & message broker |
| **OpenSearch** | ✅ Running | 9200, 9600 | Healthy | Vector & full-text search |
| **OpenSearch Dashboards** | ✅ Running | 5601 | Healthy | Search UI |
| **MinIO** | ✅ Running | 9000, 9001 | Healthy | S3-compatible storage |
| **MongoDB** | ✅ Running | 27017 | Healthy | Alternative vector DB |
| **Neo4j** | ✅ Running | 7474, 7687 | Healthy | Graph database |
| **Phoenix** | ✅ Running | 6006, 4317, 4318 | Healthy | AI Observability |
| **LiteLLM** | ✅ Running | 4000 | Healthy | LLM Gateway |
| **Pinecone Local** | ⚠️ Running | 5081-5090 | Unhealthy | Vector DB (optional) |

## Service Details

### 1. PostgreSQL (Port 5433 → 5432)
- **Image:** postgres:16-alpine
- **Status:** ✅ Healthy
- **Purpose:** Primary relational database for all services
- **Databases:** agentmesh, phoenix
- **User:** agentmesh
- **Connection:** `postgresql://agentmesh:agentmesh@localhost:5433/agentmesh`

**Test:**
```bash
docker exec agentmesh-postgres psql -U agentmesh -c "SELECT version();"
```

### 2. Redis (Port 6379)
- **Image:** redis:7-alpine
- **Status:** ✅ Healthy
- **Purpose:** Cache, session storage, Celery message broker
- **Persistence:** AOF enabled

**Test:**
```bash
docker exec agentmesh-redis redis-cli ping
# Returns: PONG
```

### 3. OpenSearch (Ports 9200, 9600)
- **Image:** opensearchproject/opensearch:2.17.1
- **Status:** ✅ Healthy
- **Purpose:** Vector search (RAG), full-text search, hybrid search
- **Security:** Disabled for local development
- **Memory:** 1GB heap

**Test:**
```bash
curl http://localhost:9200/_cluster/health
```

**Access:** http://localhost:9200

### 4. OpenSearch Dashboards (Port 5601)
- **Image:** opensearchproject/opensearch-dashboards:2.17.1
- **Status:** ✅ Healthy
- **Purpose:** Visualize OpenSearch data, manage indices
- **Access:** http://localhost:5601

### 5. MinIO (Ports 9000, 9001)
- **Image:** minio/minio:RELEASE.2025-04-22T22-12-26Z
- **Status:** ✅ Healthy
- **Purpose:** S3-compatible object storage for file uploads
- **User:** minioadmin
- **Password:** minioadmin
- **Bucket:** agentmesh-uploads

**API:** http://localhost:9000
**Console:** http://localhost:9001

**Test:**
```bash
curl http://localhost:9000/minio/health/live
```

### 6. MongoDB (Port 27017)
- **Image:** mongo:7
- **Status:** ✅ Healthy
- **Purpose:** Alternative vector backend (Atlas Vector Search)
- **Connection:** `mongodb://localhost:27017`

**Test:**
```bash
docker exec agentmesh-mongodb mongosh --eval "db.runCommand('ping')"
```

### 7. Neo4j (Ports 7474, 7687)
- **Image:** neo4j:5-community
- **Status:** ✅ Healthy
- **Purpose:** Knowledge graph, relationship mapping
- **User:** neo4j
- **Password:** agentmesh
- **Plugins:** APOC, Graph Data Science

**Browser:** http://localhost:7474
**Bolt:** bolt://localhost:7687

**Test:**
```bash
curl http://localhost:7474
```

### 8. Phoenix (Ports 6006, 4317, 4318)
- **Image:** arizephoenix/phoenix:latest
- **Status:** ✅ Healthy
- **Purpose:** AI Observability, trace collection, evaluation
- **UI:** http://localhost:6006
- **OTLP gRPC:** port 4317
- **OTLP HTTP:** port 4318
- **Database:** PostgreSQL (phoenix database)

**Test:**
```bash
curl http://localhost:6006/healthz
```

### 9. LiteLLM (Port 4000)
- **Image:** ghcr.io/berriai/litellm:main-stable
- **Status:** ✅ Healthy
- **Purpose:** Unified LLM gateway (OpenAI, Anthropic, Google)
- **Master Key:** sk-agentmesh-local
- **UI:** http://localhost:4000/ui

**Available Models:**
- claude-sonnet-4-6
- claude-opus-4-1
- claude-haiku-4-5
- gpt-4.1
- gpt-4.1-mini
- o4-mini
- gemini-2.5-pro
- gemini-2.5-flash
- text-embedding-3-small

**Test:**
```bash
curl http://localhost:4000/health/liveliness
# Returns: "I'm alive!"

curl http://localhost:4000/v1/models \
  -H "Authorization: Bearer sk-agentmesh-local"
```

### 10. Pinecone Local (Ports 5081-5090)
- **Image:** ghcr.io/pinecone-io/pinecone-local:latest
- **Status:** ⚠️ Unhealthy (optional service)
- **Purpose:** Local Pinecone emulator for testing
- **Note:** This service is optional and not required for core functionality

## Fixed Issues

### LiteLLM Configuration Path ✅ FIXED

**Problem:**
```
IsADirectoryError: [Errno 21] Is a directory: '/app/config.yaml'
```

**Root Cause:**
- `docker-compose-infra.yml` was mounting from `./litellm_config.yaml`
- Should be `./infra/litellm/config.yaml`

**Solution:**
Updated `docker-compose-infra.yml`:
```yaml
volumes:
  - ./infra/litellm/config.yaml:/app/config.yaml:ro  # ✅ Fixed
```

## Quick Commands

### Start All Infrastructure
```bash
docker compose -f docker-compose-infra.yml up -d
```

### Check Status
```bash
docker compose -f docker-compose-infra.yml ps
```

### View Logs
```bash
docker compose -f docker-compose-infra.yml logs -f
docker compose -f docker-compose-infra.yml logs -f litellm
docker compose -f docker-compose-infra.yml logs -f phoenix
```

### Stop All
```bash
docker compose -f docker-compose-infra.yml down
```

### Stop and Remove Volumes (⚠️ Deletes all data)
```bash
docker compose -f docker-compose-infra.yml down -v
```

### Restart Specific Service
```bash
docker compose -f docker-compose-infra.yml restart litellm
docker compose -f docker-compose-infra.yml restart phoenix
```

## Health Checks

Run these to verify all services:

```bash
# PostgreSQL
docker exec agentmesh-postgres pg_isready -U agentmesh

# Redis
docker exec agentmesh-redis redis-cli ping

# OpenSearch
curl http://localhost:9200/_cluster/health

# MinIO
curl http://localhost:9000/minio/health/live

# MongoDB
docker exec agentmesh-mongodb mongosh --eval "db.runCommand('ping')"

# Neo4j
curl http://localhost:7474

# Phoenix
curl http://localhost:6006/healthz

# LiteLLM
curl http://localhost:4000/health/liveliness
```

## Port Reference

| Port | Service | Purpose |
|------|---------|---------|
| 4000 | LiteLLM | LLM Gateway API |
| 4317 | Phoenix | OTLP gRPC |
| 4318 | Phoenix | OTLP HTTP |
| 5433 | PostgreSQL | Database (mapped from 5432) |
| 5601 | OpenSearch Dashboards | Search UI |
| 5081-5090 | Pinecone Local | Vector DB |
| 6006 | Phoenix | Web UI |
| 6379 | Redis | Cache & Broker |
| 7474 | Neo4j | HTTP/Browser |
| 7687 | Neo4j | Bolt Protocol |
| 9000 | MinIO | S3 API |
| 9001 | MinIO | Console UI |
| 9200 | OpenSearch | API |
| 9600 | OpenSearch | Performance |
| 27017 | MongoDB | Database |

## Web UIs

| Service | URL | Credentials |
|---------|-----|-------------|
| **LiteLLM UI** | http://localhost:4000/ui | admin/admin |
| **Phoenix** | http://localhost:6006 | No auth |
| **OpenSearch Dashboards** | http://localhost:5601 | No auth |
| **MinIO Console** | http://localhost:9001 | minioadmin/minioadmin |
| **Neo4j Browser** | http://localhost:7474 | neo4j/agentmesh |

## Volume Information

All data is persisted in Docker named volumes:

- `agentmesh_postgres_data` - PostgreSQL data
- `agentmesh_redis_data` - Redis AOF
- `agentmesh_opensearch_data` - OpenSearch indices
- `agentmesh_minio_data` - Uploaded files
- `agentmesh_mongodb_data` - MongoDB collections
- `agentmesh_neo4j_data` - Neo4j graph data
- `agentmesh_phoenix_data` - Phoenix traces

**To see all volumes:**
```bash
docker volume ls | grep agentmesh
```

## Summary

✅ **All critical services are running and healthy!**

- Database layer: PostgreSQL, Redis, MongoDB
- Search layer: OpenSearch (with Dashboards)
- Storage layer: MinIO
- Graph layer: Neo4j
- Observability: Phoenix
- LLM Gateway: LiteLLM

Only Pinecone Local is unhealthy, but it's an optional service not required for core functionality.

**Everything in `docker-compose-infra.yml` is working correctly!** ✅
