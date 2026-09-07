# AgentMesh

A production-grade multi-agent orchestration platform where the framework is a runtime setting, not an architectural commitment. Seven interchangeable agent runtimes, five specialist agents, eight tools, hybrid RAG, dual-layer memory, a full ingestion pipeline, and the resilience stack a production system actually needs — circuit breakers, retries, rate limiting, structured observability — all running behind a single event contract that the React console, the database and the API never learn to distinguish.

```
React console  ──>  FastAPI  ──>  Agent runtime  ──>  ┌ Google ADK (declarative pipeline)
   (SSE)              |                               ├ Google ADK (graph Workflow)
                      |                               ├ LangGraph (supervisor graph)
                      |                               ├ LangChain DeepAgents (planning-first)
                      |                               ├ Claude Agent SDK (MCP tools)
                      |                               ├ Microsoft Agent Framework (GroupChat)
                      |                               └ AWS Strands Agents (Swarm)
```

---

## Table of contents

- [Tech stack](#tech-stack)
- [Why this exists](#why-this-exists)
- [Quickstart](#quickstart)
- [Docker Compose services](#docker-compose-services)
- [Architecture deep dive](#architecture-deep-dive)
- [The seven runtimes](#the-seven-runtimes)
- [The five agents and their tools](#the-five-agents-and-their-tools)
- [Resilience engineering](#resilience-engineering)
- [Hybrid RAG retrieval](#hybrid-rag-retrieval)
- [Memory system](#memory-system)
- [Document ingestion pipeline](#document-ingestion-pipeline)
- [Observability stack](#observability-stack)
- [Streaming protocol](#streaming-protocol)
- [The frontend](#the-frontend)
- [Database schema](#database-schema)
- [API reference](#api-reference)
- [Configuration reference](#configuration-reference)
- [Project layout](#project-layout)
- [Running in production](#running-in-production)
- [Extending it](#extending-it)

**📚 [Complete Documentation Index](docs/INDEX.md)**

---

## Tech stack

| Layer | Tool | Role in AgentMesh |
|---|---|---|
| API framework | **FastAPI** | Async HTTP server, SSE streaming, OpenAPI docs, Pydantic validation |
| Graph orchestration | **LangGraph** | Default runtime: explicit `StateGraph` with structured-output supervisor and parallel fan-out |
| Declarative orchestration | **Google ADK 2.x** | Two runtimes: `SequentialAgent`/`ParallelAgent`/`LoopAgent` pipeline + graph `Workflow` with `JoinNode` and HITL gates |
| Planning-first orchestration | **LangChain DeepAgents** | Open-ended research: virtual filesystem, subagent spawning, todo/planning tools |
| Claude-native orchestration | **Claude Agent SDK** | In-process MCP server, programmatic subagents, Anthropic context management |
| GroupChat orchestration | **Microsoft Agent Framework** | Round-robin `GroupChat` with custom `BaseChatClient` wrapping OpenAI 1.x SDK |
| Swarm orchestration | **AWS Strands Agents** | `Swarm` with `LiteLLMModel`, shared context, autonomous handoffs between specialists |
| LLM providers | **OpenAI** / **Anthropic** / **Google GenAI** | Claude Sonnet 4.6, GPT-4.1, Gemini 2.5 Pro (configurable per request) |
| LLM routing | **LiteLLM** | Unified `provider/model` format for ADK, Strands, and MS Agent runtimes |
| LLM gateway | **LiteLLM Proxy** (Docker service) | Single egress point for all model traffic — latency-based routing, cross-provider fallbacks, spend tracking, unified logging (port 4000) |
| Embeddings | **OpenAI text-embedding-3-small** | Default embedding model for RAG and long-term memory (via `langchain-openai` or LiteLLM proxy) |
| RAG retrieval (default) | **OpenSearch 2.17** | Hybrid BM25 + kNN (HNSW/Lucene) fused by Reciprocal Rank Fusion |
| RAG retrieval (alt) | **MongoDB 7** + **Atlas Vector Search** | Config-driven alternative: `$vectorSearch` + `$text` with RRF fusion (set `VECTOR_BACKEND=mongodb`) |
| Reranking | **sentence-transformers** (`ms-marco-MiniLM-L-6-v2`) | Optional cross-encoder reranking on the fused head |
| Short-term memory | **PostgreSQL 16** + **SQLAlchemy asyncio** + **asyncpg** | Full conversation transcript, agent steps, rolling summary |
| Long-term memory | **OpenSearch** or **MongoDB** (semantic index) | LLM-extracted durable facts, embedded for cross-conversation recall (backend follows `VECTOR_BACKEND`) |
| Session memory | **ADK DatabaseSessionService** + **Postgres** | ADK session persistence (declarative pipeline + graph workflow runtimes) |
| Task queue | **Celery 5.5** + **Redis 7** | Document ingestion workers with `acks_late`, deterministic chunk ids, backoff retries |
| Object storage | **MinIO** / **S3** (via **boto3**) | Uploaded documents, presigned download URLs |
| Database ORM | **SQLAlchemy 2.0** (async) + **Alembic** | 9 models, async repositories, JSONB with GIN indexes, migration chain |
| MongoDB driver | **motor** (async) + **pymongo** (sync) | Atlas Vector Search for RAG, async for API server, sync for Celery workers |
| Auth | **Header-based** (`X-User-ID`) | Seam for JWT/OIDC; everything downstream takes a user id string |
| Rate limiting (global) | **Custom sliding-window middleware** | Per-user, in-process, skips health/docs paths |
| Rate limiting (per-endpoint) | **slowapi** | Granular limits: chat 30/min, uploads 20/min, search 60/min |
| Retries (custom) | **Custom `retry_async`** | Exponential backoff with full jitter, `is_retryable()` classification |
| Retries (industry) | **tenacity** | `AsyncRetrying` with `wait_exponential_jitter`, composable decorators |
| Circuit breaking (custom) | **Custom `CircuitBreaker`** | Async three-state (closed/open/half-open), capped half-open probes, introspectable via `/health` |
| Circuit breaking (industry) | **pybreaker** | Standard three-state breakers with `_PybreakerListener` for structured logging |
| Bulkhead | **Custom `Bulkhead`** | `asyncio.Semaphore`-based concurrency cap per dependency |
| PII scanning | **Regex-based `pii_scan` tool** | Email, SSN, phone, credit card, IP, IBAN detection + redaction |
| Policy compliance | **`policy_lookup` tool** | Citation, PII, financial advice, uncertainty, retention rules |
| Web search | **Tavily** + **DuckDuckGo** (`ddgs`) | Auto mode: try Tavily first, fall back to DuckDuckGo (no API key needed) |
| MCP integration | **mcp** SDK + **fastmcp** + **langchain-mcp-adapters** | Claude SDK in-process MCP server for tool exposure |
| HTTP client | **httpx** | Async HTTP for Tavily, provider APIs, outgoing requests |
| Observability (LLM) | **Arize Phoenix** (OTLP gRPC) | Traces every LLM call, tool invocation, and agent handoff via OpenInference spans |
| Observability (alt) | **Opik** (Comet) | Parallel tracing: OpenAI, LiteLLM, LangChain callbacks to self-hosted Opik |
| Observability (OTEL) | **OpenTelemetry SDK** | `BatchSpanProcessor` to Phoenix; instruments FastAPI, httpx, OpenAI, Anthropic, LiteLLM, GenAI, ADK, Bedrock, LangChain |
| Observability (app) | **structlog** | JSON-structured logging with `request_id`, `conversation_id`, `user_id` from contextvars |
| Metrics | **prometheus-client** | Prometheus-format metrics endpoint |
| Graph database | **Neo4j 5** | Connection configured, driver in requirements (knowledge graph integration point) |
| Vector database | **Pinecone Local** | In-memory emulator for local dev; `langchain-pinecone` for notebook experiments |
| Document parsing | **pypdf** + **python-docx** + **openpyxl** + **beautifulsoup4** | PDF (+ OCR via tesseract), DOCX, XLSX, CSV, HTML, JSON, Markdown |
| Chunking | **Custom recursive splitter** | Structural boundaries (`## `, `# `, paragraph, sentence), page-aware, configurable overlap |
| Frontend framework | **React 18** + **Vite** | Three-pane console: threads rail, transcript + composer, inspector (Trace/Config/Files) |
| Frontend streaming | **fetch + ReadableStream** | SSE reader (not EventSource, because POST body + custom headers are needed) |
| Container runtime | **Docker Compose v2** | 10+ services with healthchecks, dependency ordering, named volumes |
| Reverse proxy | **nginx** | Frontend static files, SSE proxy with `proxy_buffering off` |

---

## Why this exists

Most multi-agent codebases marry one framework. The framework's session object becomes the conversation, its event type becomes the API contract, its state model becomes the schema. Switching later means a rewrite, and comparing two frameworks honestly means building the same thing twice.

AgentMesh puts a single event contract in the middle. `app/agents/base.py` defines the vocabulary — `plan`, `agent_started`, `tool_call`, `tool_result`, `token`, `citation`, `handoff`, `usage`, `error`, `run_finished` — and each framework adapter translates into it. Everything above the adapter (the API, the database, the React client) sees one stream and never learns which runtime ran.

Two things follow:

- You can A/B two frameworks on the same question, with the same prompts and the same tools, and the difference you measure is the framework.
- Adding an eighth means implementing one class. Nothing else changes.

The rest of the stack — Postgres, OpenSearch, Redis/Celery, MinIO, circuit breakers, an audit trail, dual observability platforms — is what makes the comparison meaningful under load rather than a demo.

---

## Quickstart

**You need:** Docker with Compose v2, about 6 GB of free RAM (OpenSearch takes most of it), and at least one model provider API key.

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY (or OPENAI_API_KEY / GOOGLE_API_KEY).
# Also set OPENAI_API_KEY if you want retrieval — the default embedding
# model is OpenAI's, independently of which chat model you pick.

make up
```

`make up` builds the images, waits for the backend to report healthy, and runs the migrations. Then:

| What | Where |
|---|---|
| Console | http://localhost:8080 |
| API docs | http://localhost:8000/docs |
| Phoenix UI | http://localhost:6006 |
| LiteLLM UI | http://localhost:4000/ui |
| MinIO console | http://localhost:9001 (`minioadmin` / `minioadmin`) |
| Neo4j Browser | http://localhost:7474 |
| OpenSearch Dashboards | http://localhost:5601 (run `make tools`) |
| Flower | http://localhost:5555 (run `make tools`) |

Verify end to end:

```bash
make seed     # uploads a sample document, waits for it to index
make smoke    # checks health, dependencies, frameworks, and a live chat turn
```

### Without Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Point POSTGRES_HOST / OPENSEARCH_HOST / REDIS_HOST at your own services.
alembic upgrade head
uvicorn app.main:app --reload

# Worker (separate terminal):
celery -A app.ingestion.celery_app.celery_app worker -Q ingest,default --loglevel=INFO

# UI (third terminal):
cd frontend && npm install && npm run dev     # http://localhost:5173
```

---

## Docker Compose services

The full local stack runs 14 active services plus one init container. Every service has a healthcheck and every dependent waits on it, so `docker compose up -d` is deterministic.

### Core application

| Service | Container | Image | Ports | Role | Credentials / Notes |
|---|---|---|---|---|---|
| **frontend** | `agentmesh-frontend` | Custom (Vite + nginx) | `8080:80` | React console | Open http://localhost:8080 |
| **backend** | `agentmesh-backend` | Custom (FastAPI + uvicorn) | `8000:8000` | API server, SSE streaming, agent orchestration | API docs at http://localhost:8000/docs. Depends on 3 MCP servers |
| **celery-worker** | `agentmesh-worker` | Same as backend | none | Document ingestion workers (parse, chunk, embed, index) | 2 queues: `ingest`, `default`. Scale with `make scale-workers n=4` |
| **flower** | `agentmesh-flower` | Same as backend | `5555:5555` | Celery task monitoring UI | `make tools` to start. Open http://localhost:5555. Profile: `tools` |

### MCP Tool Servers

| Service | Container | Image | Ports | Role | Credentials / Notes |
|---|---|---|---|---|---|
| **mcp-documents** | `agentmesh-mcp-documents` | Custom (FastMCP) | `8081:8081` | Document management: list_documents, get_document_info, search_documents | Backend depends on this. SSE transport at `/mcp` |
| **mcp-search** | `agentmesh-mcp-search` | Custom (FastMCP) | `8082:8082` | Web search and corpus overview tools | Backend depends on this. SSE transport at `/mcp` |
| **mcp-memory** | `agentmesh-mcp-memory` | Custom (FastMCP) | `8083:8083` | Long-term memory: recall_memories, store_memory, forget_memory | Backend depends on this. SSE transport at `/mcp` |

### LLM gateway

| Service | Container | Image | Ports | Role | Credentials / Notes |
|---|---|---|---|---|---|
| **litellm** | `agentmesh-litellm` | `ghcr.io/berriai/litellm:main-stable` | `4000:4000` | LLM proxy: routing, fallbacks, spend tracking | UI at http://localhost:4000/ui. Master key: `sk-agentmesh-local` (via `LITELLM_MASTER_KEY`). Config: `infra/litellm/config.yaml` |

### Datastores

| Service | Container | Image | Ports | Role | Credentials / Notes |
|---|---|---|---|---|---|
| **postgres** | `agentmesh-postgres` | `postgres:16-alpine` | `5432:5432` | Conversations, messages, runs, steps, documents, settings, audit logs, ADK sessions, Phoenix traces, LiteLLM spend | User: `agentmesh` / Password: `agentmesh` / DB: `agentmesh`. Connect: `psql -h localhost -U agentmesh -d agentmesh` or `make psql` |
| **redis** | `agentmesh-redis` | `redis:7-alpine` | `6379:6379` | Celery broker + result backend, rate limiting | No password (local). AOF persistence enabled |
| **opensearch** | `agentmesh-opensearch` | `opensearchproject/opensearch:2.17.1` | `9200:9200` | Default vector backend: document chunks (hybrid BM25 + kNN), long-term memory | Security plugin disabled locally. ~1 GB heap. API: http://localhost:9200 |
| **opensearch-dashboards** | `agentmesh-dashboards` | `opensearchproject/opensearch-dashboards:2.17.1` | `5601:5601` | OpenSearch visual management | Open http://localhost:5601. `make tools` profile |
| **mongodb** | `agentmesh-mongodb` | `mongo:7` | `27017:27017` | Alternative vector backend (set `VECTOR_BACKEND=mongodb`) | No auth (local). Replica set `rs0` for `$vectorSearch` support. Connect: `mongosh mongodb://localhost:27017/agentmesh` |
| **neo4j** | `agentmesh-neo4j` | `neo4j:5-community` | `7474:7474` (HTTP), `7687:7687` (Bolt) | Graph database | User: `neo4j` / Password: `agentmesh2026`. Browser: http://localhost:7474. APOC plugin enabled |
| **pinecone** | `agentmesh-pinecone` | `ghcr.io/pinecone-io/pinecone-local:latest` | `5081-5090:5081-5090` | In-memory Pinecone emulator for notebook experiments | No API key needed. Controller: http://localhost:5081. Data is in-memory (lost on restart) |

### Object storage

| Service | Container | Image | Ports | Role | Credentials / Notes |
|---|---|---|---|---|---|
| **minio** | `agentmesh-minio` | `minio/minio:RELEASE.2025-04-22T22-12-26Z` | `9000:9000` (API), `9001:9001` (Console) | S3-compatible object storage for uploaded documents | Console: http://localhost:9001. User: `minioadmin` / Password: `minioadmin`. Bucket: `agentmesh-uploads` |
| **minio-init** | `agentmesh-minio-init` | `minio/mc:RELEASE.2025-04-16T18-13-26Z` | none | One-shot: creates the upload bucket on first start | Runs once and exits |

### Observability

| Service | Container | Image | Ports | Role | Credentials / Notes |
|---|---|---|---|---|---|
| **phoenix** | `agentmesh-phoenix` | `arizephoenix/phoenix:latest` | `6006:6006` (UI), `4317:4317` (OTLP gRPC), `4318:4318` (OTLP HTTP) | AI observability: LLM traces, tool spans, agent handoffs | UI: http://localhost:6006. Stores traces in Postgres (`phoenix` database). Every LLM call across all providers and frameworks is captured |
| **opik** (disabled) | — | `ghcr.io/comet-ml/opik/*` | `5174:5174` (UI), `8083:8080` (API) | Alternative AI observability (Comet) | Requires 7 extra containers. Enable with `OPIK_ENABLED=true` + uncomment services. UI: http://localhost:5174 |

### Quick access summary

```
http://localhost:8080    Console (React UI)
http://localhost:8000    Backend API (FastAPI + /docs)
http://localhost:4000    LiteLLM Proxy (/ui for dashboard)
http://localhost:6006    Phoenix (AI traces)
http://localhost:8081    MCP Documents Server (/health)
http://localhost:8082    MCP Search Server (/health)
http://localhost:8083    MCP Memory Server (/health)
http://localhost:9001    MinIO Console (minioadmin / minioadmin)
http://localhost:7474    Neo4j Browser (neo4j / agentmesh2026)
http://localhost:5601    OpenSearch Dashboards (make tools)
http://localhost:5555    Flower (make tools)
http://localhost:5081    Pinecone Local controller
http://localhost:9200    OpenSearch API
http://localhost:27017   MongoDB (mongosh mongodb://localhost:27017/agentmesh)
http://localhost:5432    PostgreSQL (psql -h localhost -U agentmesh -d agentmesh)
http://localhost:6379    Redis (redis-cli)
```

### Volumes

All data survives `docker compose down`. Use `docker compose down -v` (or `make clean`) to wipe everything.

| Volume | Service | Contents |
|---|---|---|
| `pgdata` | postgres | All Postgres databases (agentmesh, phoenix, litellm) |
| `redisdata` | redis | Celery broker queues, AOF journal |
| `osdata` | opensearch | Document chunks, memory vectors, HNSW indexes |
| `miniodata` | minio | Uploaded document files |
| `neo4jdata` | neo4j | Graph database |
| `neo4jlogs` | neo4j | Neo4j server logs |
| `mongodata` | mongodb | Document chunks and memory (when `VECTOR_BACKEND=mongodb`) |

---

## Architecture deep dive

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  React console (Vite + nginx)                                               │
│  threads rail  |  transcript + composer  |  inspector: Trace / Config / Files│
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │  SSE  (POST /api/v1/chat/stream)
┌────────────────────────────────▼────────────────────────────────────────────┐
│  FastAPI                                                                    │
│  middleware: CorrelationMiddleware -> RateLimitMiddleware -> slowapi -> GZip │
│  routes: chat . conversations . runs . settings . files . search . audit    │
│                               ChatService                                   │
│       resolve config -> assemble memory -> open run -> stream -> persist     │
└────┬──────────────────┬──────────────────┬──────────────────┬───────────────┘
     │                  │                  │                  │
┌────▼────────────┐ ┌───▼──────────┐ ┌─────▼──────────┐ ┌────▼────────────────┐
│ Agent runtime   │ │ LiteLLM Proxy│ │ Memory         │ │ Retrieval           │
│ ADK pipeline    │ │ (port 4000)  │ │ short: Postgres│ │ (config-driven)     │
│ ADK workflow    │ │ routing,     │ │ long: OS or    │ │ OpenSearch (default) │
│ LangGraph       │ │ fallbacks,   │ │       MongoDB  │ │ -- or --            │
│ DeepAgents      │ │ spend track  │ │ summary: PG   │ │ MongoDB Atlas Vector │
│ Claude SDK      │ └──────┬───────┘ └────────────────┘ │ BM25+kNN -> RRF     │
│ MS Agent Frmwk  │        │                             └─────────────────────┘
│ Strands Agents  │        ▼
└────┬────────────┘  OpenAI / Anthropic / Google
     │ 8 tools, each with a breaker and a timeout
     │
┌────▼────────────────────────────────────────────────────────────────────────┐
│ Infrastructure                                                              │
│ PostgreSQL 16   OpenSearch 2.17   MongoDB 7       Redis 7 + Celery         │
│ (transcripts,   (chunks, memory   (alt vector     (ingestion queue,        │
│  runs, steps,    when OS backend)  backend)         2 queues, retries)      │
│  settings,                                                                  │
│  audit logs)    MinIO / S3        Neo4j           Pinecone Local           │
│                 (uploaded files)   (graph DB)      (notebook experiments)   │
│                                                                             │
│ Arize Phoenix (OTLP)   Opik (Comet)   LiteLLM (model gateway)             │
│ (LLM traces, spans)    (alt traces)   (routing, fallbacks, spend)          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The lifecycle of one turn

1. `POST /api/v1/chat/stream` arrives. `CorrelationMiddleware` assigns a request id and binds it to structlog's contextvars. `RateLimitMiddleware` (custom sliding-window) and slowapi (per-endpoint) both gate the request.

2. `ChatService.resolve_config` merges three sources in precedence order: **request body > user's saved settings > defaults in config.py**. This is how a user can change framework, model, temperature, or active agents per request.

3. The conversation is created or loaded. The user's message is written to Postgres **before any model is called**, so a crashed run still leaves a record of what was asked.

4. Memory is assembled:
   - Last N turns from Postgres (`ShortTermMemory.window()`, default 20)
   - Rolling summary if the thread outgrew the window
   - Semantically recalled long-term memories from OpenSearch or MongoDB (if enabled, follows `VECTOR_BACKEND`)

5. An `agent_runs` row is opened and **committed immediately**. If the process dies mid-stream, the run is still visible with status `running` rather than vanishing silently.

6. `get_runtime(framework)` returns the cached adapter. The runtime's `stream()` yields `AgentEvent`s. The service forwards each one to the client as SSE while collecting text, citations, tool steps, and usage.

7. When the stream closes, everything is persisted in a **fresh session** — the request session may have been rolled back by whatever failed. Steps, the assistant message, usage, and citations all land in Postgres.

8. `_post_turn` fires as a background task: roll the summary forward if the thread is long, distil durable facts into long-term memory via an LLM extraction pass. The user is already reading the answer.

9. If Phoenix or Opik tracing is enabled, every LLM call, tool invocation, and agent handoff has already been recorded as OpenTelemetry spans or Opik traces in real time.

### Data flow through the resilience stack

Every external call follows this path:

```
caller -> tenacity retry (exponential backoff + jitter)
            -> pybreaker gate (three-state circuit breaker)
                -> asyncio.wait_for (per-attempt timeout)
                    -> actual call (LLM / OpenSearch / S3 / Tavily / DuckDuckGo)
```

The custom resilience primitives (`resilience.py`) run the same composition: `retry_async -> CircuitBreaker.call -> asyncio.wait_for`. Both systems operate in parallel — the custom breakers provide async-native half-open probe semantics and feed `/health`, while tenacity + pybreaker provide the industry-standard libraries that ops teams already know.

---

## The seven runtimes

All seven get the same five agents, the same eight tools, the same prompts, and the same memory block. They differ only in how orchestration is expressed.

### 1. LangGraph — explicit supervisor graph (default)

```
START -> supervisor -+-> researcher -+
                     +-> retriever  -+-> fan_in -> supervisor
                     +-> analyst -----------------> supervisor
                     +-> compliance --------------> supervisor
                     +-> writer ------------------> END
```

The supervisor uses structured output (`Route` Pydantic model), not free text. `researcher` and `retriever` fan out in parallel. Each specialist runs a tool loop bounded at 3 passes. Every `tool_call` id gets a matching `tool` message — dangling ids cause the next provider call to reject the whole conversation.

### 2. Google ADK — declarative pipeline (ADK 2.x)

```
SequentialAgent "agentmesh_pipeline"
  1. ParallelAgent "discovery"    -> researcher || retriever
  2. LlmAgent      "analyst"
  3. LoopAgent     "review_cycle" -> compliance -> writer  (max 2 iterations)
```

State flows through `output_key`: each agent writes to a named key, the next reads via `{key?}` templating. The `LoopAgent` terminates early when compliance calls `exit_review`. Sessions persist through ADK's `DatabaseSessionService` on Postgres, with in-memory fallback.

### 3. Google ADK — graph Workflow

```
START -+-> researcher -+
       +-> retriever  -+-> JoinNode -> classify_and_route
       +-> analyst    -+                    |
                          +------+----------+--------+-------------+
                        "tech"  "billing" "compliance"  "general"
                          |        |           |            |
                   troubleshoot  billing   compliance    writer
                   (loop via     agent     agent        agent
                    ctx.run_node)  |
                                hitl_gate
```

Explicit graph with `JoinNode` for parallel fan-out fusion, conditional routing based on session state, dynamic troubleshooting loops, and HITL (human-in-the-loop) gates where missing approval pauses the workflow.

### 4. LangChain DeepAgents — planning-first

The opposite philosophy. One capable agent gets a planning tool, a virtual filesystem, and a roster of subagents. It decides the workflow at runtime. Long intermediate material gets written to a file instead of carried in context, which prevents window exhaustion on long research runs.

### 5. Claude Agent SDK — Anthropic's harness

Uses `ClaudeSDKClient` with `ClaudeAgentOptions`. Our tools are exposed through an **in-process MCP server** (`create_sdk_mcp_server`) — no subprocess, no IPC, tool calls land directly in the FastAPI event loop. The five specialists become programmatic subagents. This runtime talks to Claude models only.

### 6. Microsoft Agent Framework — GroupChat

All specialists sit in a shared transcript and iteratively refine each other's work until Writer produces a final answer or the round cap is hit. Uses a custom `BaseChatClient` wrapping the OpenAI 1.x SDK; for Anthropic/Google it routes through LiteLLM's OpenAI-compatibility layer. Tool results are pre-executed and injected as context.

### 7. AWS Strands Agents — Swarm

```
   orchestrator --handoff--> researcher
       ^                         |
       |                    handoff
   writer <----- compliance <-- analyst <-- retriever
```

Specialists collaborate through shared context with autonomous handoffs via `handoff_to_agent`. Uses `LiteLLMModel` for provider routing. Runs the swarm synchronously in a thread executor (Strands agents are sync), with a custom callback handler that feeds events into an `asyncio.Queue`.

### Choosing between them

| | LangGraph | ADK Pipeline | ADK Workflow | DeepAgents | Claude SDK | MS Agent | Strands |
|---|---|---|---|---|---|---|---|
| Control flow | explicit graph | declarative | explicit graph | model-decided | model-decided | round-robin chat | autonomous handoffs |
| Predictability | high | high | high | moderate | moderate | moderate | moderate |
| Parallelism | fan-out edges | `ParallelAgent` | `JoinNode` | subagent spawning | subagent spawning | sequential | Swarm coordination |
| HITL support | - | - | gate nodes | - | - | - | - |
| Best for | known workflows | stable pipelines | complex routing | open-ended research | Claude models | iterative refinement | collaborative teams |
| Providers | all three | all three | all three | all three | Anthropic only | all three (LiteLLM) | all three (LiteLLM) |

---

## The five agents and their tools

Prompts live in one file — `app/agents/definitions.py` — and every framework reads from it. A wording change lands in all seven runtimes at once.

| Agent | Job | Tools |
|---|---|---|
| **Orchestrator** | Plans, routes, merges, owns the final answer | delegation only |
| **Researcher** | External and corpus-level discovery | `web_search`, `corpus_overview` |
| **Retriever** | Hybrid RAG over the user's documents, returns cited passages | `hybrid_search`, `fetch_document_chunk` |
| **Analyst** | Arithmetic, quantitative reasoning, tabular data | `calculator`, `table_stats` |
| **Compliance** | PII screening, policy review, unsupported-claim detection | `pii_scan`, `policy_lookup` |
| **Writer** | Final composition with citations intact | none |

The first routing rule matters most in practice:

> A greeting or a trivial question needs no delegation. Answer it and stop. Spinning up five agents for 'hi' is a bug, not thoroughness.

### Tool implementation pattern

Tools are plain async functions in `app/agents/tools/core.py`. The adapters in `adapters.py` wrap them into LangChain `StructuredTool`s, ADK `FunctionTool`s, or Claude SDK MCP tools — the logic is written once. Every wrapper adds:

1. A **per-tool circuit breaker** (both custom and pybreaker)
2. A **timeout** (`asyncio.wait_for`)
3. A **structured log line** with input preview, output length, and duration

A tool that starts failing degrades into a recoverable JSON error the agent can react to, rather than an exception that kills the run.

---

## Resilience engineering

AgentMesh runs two resilience stacks in parallel: a custom async-native implementation and the industry-standard tenacity + pybreaker libraries. Both read from the same `ResilienceSettings`.

### Custom stack (`core/resilience.py`)

**Hand-rolled for three reasons:**

1. **Capped half-open probes.** Most breaker libraries release every waiting caller when the reset timeout expires. AgentMesh caps concurrent probes at `half_open_max_calls` and requires `success_threshold` consecutive successes before closing.

2. **Selective tripping.** `is_retryable()` decides what counts. A 400 from a provider means *our* payload is wrong — retrying is pointless, tripping the breaker would take down a healthy dependency because of our own bug. Only timeouts, connection errors, 429s, and 5xx count. A dedicated test (`test_breaker_ignores_non_retryable_errors`) holds that line.

3. **Introspectable.** `CircuitBreaker.snapshot()` feeds `/api/v1/health` and the UI status bar. When a breaker opens, an operator sees which one, how long, and the last error — without reading logs.

### Industry stack (`core/resilience_ext.py`)

**tenacity** — `AsyncRetrying` with `wait_exponential_jitter`, `retry_if_exception(_is_retryable)`, `stop_after_attempt`. Configured from the same settings, composable via `@tenacity_retry()` or `@with_tenacity_resilience()`.

**pybreaker** — `CircuitBreaker` instances per dependency with a `_PybreakerListener` that logs state transitions through structlog. `pybreaker_snapshot()` feeds `/health` alongside the custom breaker snapshot.

### Composition order

Both stacks compose **timeout -> breaker -> retry** deliberately:

- Timeout innermost, so each attempt gets its own budget.
- Breaker inside the retry loop, so a tripped circuit short-circuits every attempt immediately.

Reversing this gives you a retry loop that spends its entire budget hammering a dependency already known to be down.

### Per-endpoint rate limiting (slowapi)

slowapi provides granular per-endpoint limits declared as decorators:

| Endpoint | Limit |
|---|---|
| `POST /chat/stream` | 30/minute per user |
| `POST /chat` | 30/minute per user |
| `POST /files` | 20/minute per user |
| `POST /search` | 60/minute per user |

The key function prefers `X-User-ID`, falls back to client IP. The custom `RateLimitMiddleware` remains as a global 240/min safety net across all endpoints.

### What has a breaker

`llm.openai`, `llm.anthropic`, `llm.google`, `opensearch`, `object_storage`, `embeddings`, and one per tool (`tool.hybrid_search`, `tool.web_search`, `tool.duckduckgo`, ...).

---

## Hybrid RAG retrieval

Two retrieval backends, selected by `VECTOR_BACKEND`:

| Backend | Set via | Best for |
|---|---|---|
| **OpenSearch** (default) | `VECTOR_BACKEND=opensearch` | Full hybrid BM25 + kNN with HNSW, mature tuning knobs |
| **MongoDB Atlas Vector Search** | `VECTOR_BACKEND=mongodb` | Teams already on MongoDB Atlas, simpler ops footprint |

Both backends use the same RRF fusion, the same `SearchHit` dataclass, and the same reranking path. The dispatch happens in `hybrid_search()` — everything above it (tools, agents, memory) is backend-agnostic.

### OpenSearch path (default)

Two independent queries — BM25 and kNN — fused by **Reciprocal Rank Fusion**:

```
score(d) = Sum  1 / (k + rank_i(d))          k = 60 by default
```

### Why RRF over weighted score fusion

BM25 scores are unbounded and corpus-relative — the same query against the same document scores differently after you ingest a hundred more documents, because IDF moved. Cosine similarity is bounded and absolute. Normalising them onto a shared scale gives you a blend whose effective weighting drifts as the corpus grows, silently. You find out as "retrieval got worse this quarter" with no single change to blame.

RRF looks only at ranks. Rank 1 in either leg contributes the same today and after ten thousand more documents. The cost is that it discards magnitude. For a growing corpus that is the right trade.

### Graceful degradation

The two legs run concurrently via `asyncio.gather` with `return_exceptions=True`. If the embedding provider is down, retrieval degrades to BM25-only with a logged warning. Only when both legs fail does it raise.

Optional cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`) runs on the fused head. Off by default — it roughly doubles p95 retrieval latency.

### MongoDB path

When `VECTOR_BACKEND=mongodb`, the same hybrid pattern runs against MongoDB:

- **Vector leg**: `$vectorSearch` aggregation stage (Atlas) with cosine similarity, pre-filtered by `user_id`. Falls back to brute-force cosine on local dev (no Atlas Search indexes).
- **Text leg**: `$text` search with `textScore`, falling back to regex if no text index exists.
- **Fusion**: Same RRF as OpenSearch, same `SearchHit` output. Tools and agents see no difference.

Ingestion writes chunks as MongoDB documents with the same deterministic `_id` pattern (`{document_id}:{chunk.index}`), so idempotency works identically.

Local dev runs a single-node replica set (`--replSet rs0`) so `$vectorSearch` stages are accepted. Production should point `MONGODB_URI` at Atlas.

```bash
# Switch to MongoDB backend:
VECTOR_BACKEND=mongodb docker compose up -d
```

---

## LiteLLM gateway

All LLM traffic goes through a **LiteLLM Proxy** container (port 4000) when `LITELLM_ENABLED=true` (the default in Docker).

```
backend  ──(OpenAI-compatible API)──>  litellm:4000  ──>  OpenAI / Anthropic / Google
                                           │
                                    routing, fallbacks,
                                    spend tracking, logging
```

### Why a separate gateway

1. **Provider swap without code changes.** The proxy resolves model names (`claude-sonnet-4-6`, `gpt-4.1`, `gemini-2.5-pro`) to the right provider endpoint. Adding a new provider or switching a model is a YAML change in `infra/litellm/config.yaml`.

2. **Cross-provider fallbacks.** If Anthropic is down, the proxy automatically tries OpenAI then Google, configured as fallback chains.

3. **Spend tracking.** Every call is logged with tokens, cost, and latency. The `/spend/logs` endpoint gives you a spend report without custom accounting code.

4. **Latency-based routing.** When multiple deployments serve the same logical model, the proxy routes to the fastest one.

### Configuration

`infra/litellm/config.yaml` defines:
- `model_list` — 8 models across 3 providers + embeddings
- `router_settings` — latency-based routing, 2 retries, 30s cooldown, fallback chains
- `litellm_settings` — drop unsupported params, JSON logging, request timeout
- `general_settings` — master key, max parallel requests, health check interval

### How the backend connects

When `LITELLM_ENABLED=true`, `build_chat_model()` in `llm/registry.py` routes ALL providers through a single `ChatOpenAI` pointed at `litellm:4000/v1`, using the LiteLLM master key. `resolve_adk_model()` routes through `LiteLlm` with the proxy's `api_base`. `EmbeddingClient` routes embeddings through the same proxy. When `LITELLM_ENABLED=false`, the original direct-to-provider paths are used — zero behavioral change.

### Admin endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/admin/litellm/models` | List all models the proxy can serve |
| `GET` | `/admin/litellm/health` | Proxy container health |
| `POST` | `/admin/litellm/chat` | Test completion through the proxy |
| `GET` | `/admin/litellm/spend` | Spend tracking logs |

---

## Memory system

Two stores doing two different jobs.

### Short-term — Postgres

Everything lands here: every message, every agent step, every tool call, with a JSONB `metadata` column carrying citations, routing decisions, usage and the request id. A GIN index makes that column queryable.

The prompt window is a **view** over this (`ShortTermMemory.window()`, default 20 turns). When the thread outgrows the window, older turns are folded into a **rolling summary** stored on the conversation row. Summarisation runs after the turn, never on the request path.

### Long-term — OpenSearch or MongoDB

After a turn, a separate LLM pass extracts durable facts (preferences, decisions, constraints) and indexes them with embeddings. In a later conversation sharing no keywords, `recall()` finds them semantically.

The backend follows `VECTOR_BACKEND` — OpenSearch by default, MongoDB when configured. The `LongTermMemory` class dispatches writes, recalls, and deletes to the active backend transparently.

Rules: it runs off the request path (`_post_turn` background task), and most turns extract nothing (the extraction prompt says so explicitly — a memory store that saves everything is one nobody can retrieve from).

Tenant isolation is a query constraint inside the kNN filter clause, not a post-filter. `LongTermMemory.forget()` supports deletion by memory id or whole conversation.

---

## Document ingestion pipeline

```
upload -> checksum -> MinIO/S3 -> Redis queue -> Celery worker
       -> parse -> chunk -> embed (batched) -> bulk index -> status to Postgres
```

The request path does the minimum: checksum the bytes, store them, write a row, enqueue. A `202` means *accepted*, not *searchable*. The indexing step routes to OpenSearch or MongoDB based on `VECTOR_BACKEND`.

### Parsers

PDF (with OCR fallback via tesseract), DOCX (paragraphs + tables), XLSX (per-sheet), CSV, HTML (script/style stripped), JSON (pretty-printed), Markdown, plain text. Every parser degrades to text decoding rather than raising.

### Chunking

Recursive splitting on structural boundaries (`\n## `, `\n# `, paragraph, line, sentence) with configurable overlap (default 180 chars). Page-aware — that is what lets citations carry a page number.

### Idempotency

Chunk ids are deterministic: `"{document_id}:{chunk.index}"`. Combined with `acks_late=True` + `reject_on_worker_lost=True`, a worker that dies gets the task redelivered, and the retry overwrites the same documents. Without deterministic ids, every interrupted document would duplicate — and duplicates in a RAG index crowd out other sources in the top-k.

Other worker settings: `worker_prefetch_multiplier=1` (long tasks — don't hoard), `worker_max_tasks_per_child=50` (PDF parsers leak; recycling is cheaper than hunting).

---

## Observability stack

### Arize Phoenix (primary)

OpenTelemetry SDK with `BatchSpanProcessor` exporting via OTLP gRPC to Phoenix (port 4317). Instruments:

| Component | Instrumentor |
|---|---|
| FastAPI | `opentelemetry-instrumentation-fastapi` |
| httpx | `opentelemetry-instrumentation-httpx` |
| OpenAI SDK | `openinference-instrumentation-openai` |
| Anthropic SDK | `openinference-instrumentation-anthropic` |
| LangChain / LangGraph | `openinference-instrumentation-langchain` |
| LiteLLM | `openinference-instrumentation-litellm` |
| Google GenAI SDK | `openinference-instrumentation-google-genai` |
| Google ADK | `openinference-instrumentation-google-adk` |
| AWS Bedrock | `openinference-instrumentation-bedrock` |

Every LLM call, tool invocation, and agent handoff is a span in Phoenix with prompt, response, token counts, and latency.

### Opik (secondary, optional)

Self-hosted Comet Opik running alongside Phoenix. Instruments OpenAI, LiteLLM, and LangChain via Opik's own SDK callbacks. Traces go to both platforms simultaneously.

### structlog (application logging)

Every log line carries `request_id`, `conversation_id`, and `user_id` from contextvars. JSON format in production, console format locally. A multi-agent trace is reconstructable from logs after the fact.

---

## Streaming protocol

SSE, not websockets. The traffic is one-directional — the client posts and reads until the run ends.

Three things must line up to prevent proxy buffering:
1. `X-Accel-Buffering: no` on the response
2. `proxy_buffering off` in nginx
3. A heartbeat every 15 seconds during long tool calls

The client uses `fetch` + `ReadableStream` (not `EventSource`, which cannot send POST bodies or custom headers).

Each frame is one JSON event:

```
data: {"type":"plan","agent":"orchestrator","data":{"plan":["retrieve","analyse","write"]}}
data: {"type":"tool_call","agent":"retriever","data":{"tool":"hybrid_search","input":{...}}}
data: {"type":"token","agent":"writer","data":{"text":"Revenue grew "}}
data: {"type":"run_finished","data":{"duration_ms":8421,"total_tokens":3902}}
data: [DONE]
```

---

## The frontend

Three-pane React console: threads rail, transcript + composer, and an inspector that switches between **Trace**, **Config**, and **Files**.

**Trace** — live run telemetry: handoffs, tool calls with arguments, tool results with durations, token totals. This is what makes a multi-agent system debuggable.

**Config** — every runtime knob: framework (with install status), provider, model, temperature, max tokens, active specialists, memory toggles. Settings persist per user.

**Files** — drag-and-drop upload, live ingestion status with chunk/page counts, and document scoping (the retriever searches only the selected files).

The status bar shows overall health and names any open circuit breaker.

---

## Database schema

9 SQLAlchemy models in Postgres:

| Table | Purpose | Key columns |
|---|---|---|
| `conversations` | Thread metadata | `user_id`, `framework`, `provider`, `model`, `summary`, `total_tokens` |
| `messages` | Full transcript | `conversation_id`, `seq`, `role`, `content`, `metadata` (JSONB + GIN) |
| `agent_runs` | Orchestrator invocations | `conversation_id`, `framework`, `status`, `duration_ms`, `total_tokens`, `plan` (JSONB) |
| `agent_steps` | Per-agent / tool executions | `run_id`, `agent_name`, `step_type`, `tool_name`, `input`/`output` (JSONB), `duration_ms` |
| `documents` | Uploaded files | `user_id`, `filename`, `status` (queued->parsing->chunking->embedding->indexed), `chunk_count` |
| `ingestion_jobs` | Pipeline progress | `document_id`, `stage`, `progress`, `attempt` |
| `user_settings` | Per-user preferences | `framework`, `provider`, `model`, `temperature`, `enabled_agents`, `use_long_term_memory` |
| `audit_logs` | Append-only audit trail | `action`, `resource_type`, `resource_id`, `user_id`, `detail` (JSONB) |

Migrations managed by Alembic.

---

## API reference

Base path `/api/v1`. Identity from `X-User-ID` header.

### Chat

| Method | Path | Rate limit | Notes |
|---|---|---|---|
| `POST` | `/chat/stream` | 30/min | SSE. JSON events, terminated by `[DONE]` |
| `POST` | `/chat` | 30/min | Non-streaming variant |
| `GET` | `/frameworks` | default | Seven runtimes with install status + agent roster |

### Conversations and runs

| Method | Path | Notes |
|---|---|---|
| `GET` | `/conversations` | Paginated |
| `GET` | `/conversations/{id}` | With full message history |
| `PATCH` | `/conversations/{id}` | Rename, archive, set system prompt |
| `DELETE` | `/conversations/{id}` | Cascades to messages, runs, steps |
| `GET` | `/conversations/{id}/runs` | Every orchestrator run |
| `GET` | `/runs/{id}` | One run with every agent step (replay) |

### Files and search

| Method | Path | Rate limit | Notes |
|---|---|---|---|
| `POST` | `/files` | 20/min | Multipart upload. `202` + Celery task id |
| `GET` | `/files` | default | With ingestion status, chunk/page counts |
| `POST` | `/search` | 60/min | Raw hybrid search, no agent |
| `POST` | `/files/{id}/reingest` | default | Re-run the pipeline |
| `DELETE` | `/files/{id}` | default | Removes object, row, and every chunk |

### Health

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health/live` | Liveness. Touches nothing |
| `GET` | `/health/ready` | Readiness. `503` when a dependency is down |
| `GET` | `/health` | Full detail: dependencies, breakers (custom + pybreaker), frameworks |

---

## Configuration reference

Everything is environment-driven through `app/config.py`. Every knob is typed, validated, and documented in one place.

### Agent defaults

| Variable | Default | Notes |
|---|---|---|
| `AGENT_FRAMEWORK` | `langgraph` | Any of the seven framework ids |
| `AGENT_PROVIDER` | `anthropic` | `anthropic`, `openai`, `google` |
| `AGENT_MODEL` | `claude-sonnet-4-6` | Must exist for the provider |
| `AGENT_TEMPERATURE` | `0.2` | |
| `AGENT_MAX_TOKENS` | `4096` | |
| `AGENT_MAX_ORCHESTRATOR_STEPS` | `12` | |
| `AGENT_ENABLE_LONG_TERM_MEMORY` | `true` | |

### Resilience

| Variable | Default | Notes |
|---|---|---|
| `RESILIENCE_MAX_ATTEMPTS` | `4` | Includes the first try |
| `RESILIENCE_INITIAL_BACKOFF_SECONDS` | `0.5` | |
| `RESILIENCE_FAILURE_THRESHOLD` | `5` | Consecutive failures before opening |
| `RESILIENCE_BREAKER_RESET_TIMEOUT_SECONDS` | `30` | |
| `RESILIENCE_LLM_TIMEOUT_SECONDS` | `120` | Per attempt |
| `RESILIENCE_TOOL_TIMEOUT_SECONDS` | `30` | Per attempt |
| `RESILIENCE_RATE_LIMIT_CHAT` | `30/minute` | slowapi chat endpoint limit |
| `RESILIENCE_RATE_LIMIT_UPLOAD` | `20/minute` | slowapi upload endpoint limit |
| `RESILIENCE_RATE_LIMIT_SEARCH` | `60/minute` | slowapi search endpoint limit |

### Retrieval

| Variable | Default | Notes |
|---|---|---|
| `OPENSEARCH_EMBEDDING_DIM` | `1536` | Must match the embedding model |
| `OPENSEARCH_BM25_TOP_K` | `50` | Lexical candidates |
| `OPENSEARCH_KNN_TOP_K` | `50` | Vector candidates |
| `OPENSEARCH_RRF_K` | `60` | Lower = top ranks dominate more |
| `OPENSEARCH_FINAL_TOP_K` | `8` | Passages to the agent |

### Observability

| Variable | Default | Notes |
|---|---|---|
| `PHOENIX_ENABLED` | `true` | Enable OTLP tracing to Arize Phoenix |
| `PHOENIX_HOST` | `phoenix` | Docker hostname |
| `PHOENIX_GRPC_PORT` | `4317` | OTLP gRPC port |
| `OPIK_ENABLED` | `false` | Enable Comet Opik tracing |

---

## Project layout

```
agentmesh/
├── backend/
│   ├── app/
│   │   ├── config.py               # every knob, typed and validated
│   │   ├── main.py                 # app factory, lifespan, middleware, slowapi
│   │   ├── agents/
│   │   │   ├── base.py             # AgentEvent / RunContext / AgentRuntime
│   │   │   ├── definitions.py      # the five agents, prompts written once
│   │   │   ├── registry.py         # framework selection + install probe (7 runtimes)
│   │   │   ├── service.py          # ChatService: the orchestration seam
│   │   │   ├── frameworks/
│   │   │   │   ├── adk_runtime.py            # Google ADK declarative pipeline
│   │   │   │   ├── adk_workflow_runtime.py   # Google ADK graph Workflow
│   │   │   │   ├── langgraph_runtime.py      # LangGraph supervisor graph
│   │   │   │   ├── deepagents_runtime.py     # LangChain DeepAgents
│   │   │   │   ├── claude_sdk_runtime.py     # Claude Agent SDK + MCP
│   │   │   │   ├── ms_agent_runtime.py       # Microsoft Agent Framework
│   │   │   │   └── strands_runtime.py        # AWS Strands Agents Swarm
│   │   │   └── tools/
│   │   │       ├── core.py          # 8 framework-neutral tools
│   │   │       └── adapters.py      # LangChain / ADK / Claude SDK wrappers
│   │   ├── core/
│   │   │   ├── resilience.py        # custom breaker, retry, bulkhead
│   │   │   ├── resilience_ext.py    # tenacity + pybreaker wrappers
│   │   │   ├── rate_limit.py        # slowapi Limiter + exception handler
│   │   │   ├── middleware.py        # correlation, global rate limit, error shaping
│   │   │   ├── tracing.py          # Phoenix + Opik + 10 instrumentors
│   │   │   ├── logging.py          # structlog with contextvars
│   │   │   └── errors.py           # error taxonomy (AppError, CircuitOpenError, ...)
│   │   ├── llm/
│   │   │   └── registry.py         # model provider abstraction + EmbeddingClient
│   │   ├── db/
│   │   │   ├── models.py           # 9 SQLAlchemy models
│   │   │   ├── repositories.py     # repository pattern (no raw SQL in routes)
│   │   │   └── session.py          # async session factory
│   │   ├── memory/
│   │   │   ├── short_term.py       # Postgres window + rolling summary
│   │   │   └── long_term.py        # OpenSearch semantic memory
│   │   ├── search/
│   │   │   ├── client.py           # async OpenSearch client
│   │   │   ├── hybrid.py           # BM25 || kNN -> RRF + optional reranking
│   │   │   └── indices.py          # index mappings (documents + memory)
│   │   ├── ingestion/
│   │   │   ├── celery_app.py       # Celery config (acks_late, 2 queues)
│   │   │   ├── tasks.py            # ingest_document + purge_document
│   │   │   ├── parsers.py          # PDF, DOCX, XLSX, CSV, HTML, JSON
│   │   │   └── chunking.py         # recursive structural splitter
│   │   ├── storage/
│   │   │   └── object_store.py     # S3/MinIO with breaker + retry
│   │   ├── api/v1/                 # routes (chat, files, health, settings, audit, admin)
│   │   └── schemas/                # Pydantic request/response contracts
│   ├── alembic/                    # database migrations
│   └── tests/
├── frontend/
│   └── src/
│       ├── App.jsx                 # three-pane shell
│       ├── hooks/useChat.js        # SSE state management
│       ├── lib/api.js              # fetch-based SSE reader
│       └── components/             # Transcript, Composer, Settings, Trace, Files
├── infra/                          # postgres init, opensearch, nginx configs
├── notebook/                       # Jupyter notebooks (Agentic RAG experiments)
├── scripts/                        # seed, smoke, reindex
├── docs/architecture.md
├── docker-compose.yml              # 10+ services with healthchecks
└── Makefile                        # up, down, migrate, test, lint, seed, smoke
```

---

## Running in production

The compose file runs a complete stack on a laptop. Several things in it are laptop choices.

**Authentication is a seam.** `app/api/deps.py` reads `X-User-ID`. Drop in JWT/OIDC — it touches one file.

**Turn OpenSearch security back on.** `DISABLE_SECURITY_PLUGIN=true` is for local convenience.

**Move rate limiting to Redis.** The in-process sliding window is correct for one replica. slowapi supports `redis://` as a storage URI for multi-replica deployments.

**Scale tiers independently.** The API is IO-bound. Ingestion workers are embedding-throughput-bound. OpenSearch needs memory (HNSW graphs are resident).

**Set `LOG_FORMAT=json`.** Every line carries request/conversation/user ids from contextvars.

**Back up Postgres, snapshot OpenSearch.** Postgres is the system of record. OpenSearch is derived and can be rebuilt by re-ingesting (but that costs embedding API calls).

---

## Extending it

### Add a new agent runtime

1. Subclass `AgentRuntime` in `app/agents/frameworks/`
2. Implement `stream(ctx: RunContext) -> AsyncIterator[AgentEvent]`
3. Add the framework to `AgentFramework` enum in `config.py`
4. Register it in `agents/registry.py`

Nothing else changes.

### Add a new tool

1. Write an async function in `app/agents/tools/core.py`
2. Add it to `TOOL_REGISTRY` and `TOOL_SCHEMAS`
3. Add the tool name to the relevant agent spec's `tools` list in `definitions.py`

The adapters pick it up automatically for all seven runtimes.

### Add a new LLM provider

1. Add the provider to `ModelProvider` enum
2. Add the API key to `Settings`
3. Add a branch in `build_chat_model()` and `resolve_adk_model()`
4. Add a breaker in `LLM_BREAKERS` and `pb_llm_breakers`
g