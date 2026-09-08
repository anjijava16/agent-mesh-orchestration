#!/bin/bash
# =============================================================================
# Export Local Development Environment Variables
# =============================================================================
# Usage:
#   source export-env.sh
#   OR
#   . export-env.sh
#
# This sets all environment variables in your current shell for running
# applications locally (outside Docker)
# =============================================================================

# --- Application Environment -------------------------------------------------
export ENVIRONMENT=local
export LOG_LEVEL=DEBUG
export LOG_FORMAT=console

# --- PostgreSQL (Docker → localhost) -----------------------------------------
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5433
export POSTGRES_USER=${POSTGRES_USER:-agentmesh}
export POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-agentmesh}
export POSTGRES_DB=${POSTGRES_DB:-agentmesh}

# --- OpenSearch (Docker → localhost) -----------------------------------------
export OPENSEARCH_HOST=localhost
export OPENSEARCH_PORT=9200
export OPENSEARCH_USER=admin
export OPENSEARCH_PASSWORD='Agentmesh#2026'
export OPENSEARCH_USE_SSL=false
export OPENSEARCH_EMBEDDING_DIM=1536

# --- Redis (Docker → localhost) ----------------------------------------------
export REDIS_HOST=localhost
export REDIS_PORT=6379

# --- MinIO Storage (Docker → localhost) --------------------------------------
export STORAGE_BACKEND=minio
export STORAGE_ENDPOINT_URL=http://localhost:9000
export STORAGE_ACCESS_KEY=minioadmin
export STORAGE_SECRET_KEY=minioadmin
export STORAGE_BUCKET=agentmesh-uploads

# --- Agent Configuration -----------------------------------------------------
export AGENT_FRAMEWORK=langgraph
export AGENT_PROVIDER=anthropic
export AGENT_MODEL=claude-sonnet-4-6
export AGENT_TEMPERATURE=0.2
export AGENT_ENABLE_LONG_TERM_MEMORY=true

# --- Ingestion / Embedding ---------------------------------------------------
export INGESTION_EMBEDDING_PROVIDER=openai
export INGESTION_EMBEDDING_MODEL=text-embedding-3-small
export SEARCH_PROVIDER=auto

# --- LiteLLM Proxy (Docker → localhost) --------------------------------------
export LITELLM_ENABLED=true
export LITELLM_BASE_URL=http://localhost:4000
export LITELLM_MASTER_KEY=sk-agentmesh-local

# --- MongoDB (Docker → localhost) --------------------------------------------
export VECTOR_BACKEND=opensearch
export MONGODB_URI=mongodb://localhost:27017
export MONGODB_DATABASE=agentmesh

# --- MCP Tool Servers (localhost when running locally) -----------------------
export MCP_DOCUMENTS_URL=http://localhost:8081
export MCP_SEARCH_URL=http://localhost:8082
export MCP_MEMORY_URL=http://localhost:8083

# --- Arize Phoenix (Docker → localhost) --------------------------------------
export PHOENIX_ENABLED=true
export PHOENIX_HOST=localhost
export PHOENIX_GRPC_PORT=4317
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# --- Neo4j (Docker → localhost) ----------------------------------------------
export NEO4J_URI=bolt://localhost:7687
export NEO4J_AUTH=neo4j/agentmesh

# --- Opik (Disabled by default) ----------------------------------------------
export OPIK_ENABLED=false
export OPIK_URL=http://localhost:8080
export OPIK_URL_OVERRIDE=http://localhost:8080

# --- Service URLs ------------------------------------------------------------
export BACKEND_URL=http://localhost:8000
export INGESTION_SERVICE_URL=http://localhost:8001

# --- Load API Keys from .env file --------------------------------------------
if [ -f .env ]; then
    # Export API keys from .env
    export $(grep -E "^(OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|TAVILY_API_KEY)=" .env | xargs)
    echo "✅ Loaded API keys from .env"
else
    echo "⚠️  No .env file found. API keys not loaded."
    echo "   Create .env from .env.example and add your keys."
fi

# =============================================================================
echo ""
echo "✅ Environment variables exported for local development"
echo ""
echo "Key services:"
echo "  PostgreSQL:  localhost:5432"
echo "  Redis:       localhost:6379"
echo "  OpenSearch:  localhost:9200"
echo "  MinIO:       localhost:9000"
echo "  Phoenix:     localhost:6006"
echo ""
echo "Now you can run:"
echo "  cd backend && uvicorn app.main:app --reload"
echo "  cd agentservices/ingestion/ingestion-service && uvicorn app.main:app --port 8001 --reload"
echo ""
