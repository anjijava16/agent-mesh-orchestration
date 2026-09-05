# AgentMesh

A production-shaped multi-agent platform where the orchestration framework is a
runtime setting, not an architectural commitment.

Five specialist agents — researcher, retriever, analyst, compliance reviewer,
writer — run under any of four orchestration frameworks. The agents, their
prompts, their tools, the memory model and the API contract stay identical
across all four. You change a dropdown and the same team runs on different
machinery.

```
React console  ──▶  FastAPI  ──▶  Agent runtime  ──▶  ┌ Google ADK workflows
   (SSE)                                              ├ LangGraph supervisor
                                                      ├ LangChain DeepAgents
                                                      └ Claude Agent SDK
```

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Quickstart](#quickstart)
- [Architecture](#architecture)
- [The four runtimes](#the-four-runtimes)
- [The five agents and their tools](#the-five-agents-and-their-tools)
- [Memory](#memory)
- [Hybrid search](#hybrid-search)
- [Resilience: retry and circuit breaking](#resilience-retry-and-circuit-breaking)
- [Document ingestion](#document-ingestion)
- [Streaming](#streaming)
- [The UI](#the-ui)
- [API reference](#api-reference)
- [Configuration reference](#configuration-reference)
- [Project layout](#project-layout)
- [Running it in production](#running-it-in-production)
- [Troubleshooting](#troubleshooting)
- [Extending it](#extending-it)

---

## Why this exists

Most multi-agent codebases marry one framework. The framework's session object
becomes the conversation, its event type becomes the API contract, its state
model becomes the schema. Switching later means a rewrite, and comparing two
frameworks honestly means building the same thing twice.

This one puts a single event contract in the middle. `app/agents/base.py`
defines the vocabulary — `plan`, `agent_started`, `tool_call`, `tool_result`,
`token`, `citation`, `handoff`, `usage`, `error`, `run_finished` — and each
framework adapter translates into it. Everything above the adapter (the API, the
database, the React client) sees one stream and never learns which runtime ran.

Two things follow from that:

- You can A/B two frameworks on the same question, with the same prompts and the
  same tools, and the difference you measure is the framework.
- Adding a fifth means implementing one class. Nothing else changes.

The rest of the stack — Postgres, OpenSearch, Redis/Celery, MinIO, circuit
breakers, an audit trail — is what makes the comparison meaningful under load
rather than a demo.

---

## Quickstart

**You need:** Docker with Compose v2, about 6 GB of free RAM (OpenSearch takes
most of it), and at least one model provider API key.

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY (or OPENAI_API_KEY / GOOGLE_API_KEY).
# Also set OPENAI_API_KEY if you want retrieval — the default embedding
# model is OpenAI's, independently of which chat model you pick.

make up
```

`make up` builds the images, waits for the backend to report healthy, and runs
the migrations. Then:

| What | Where |
|---|---|
| Console | http://localhost:8080 |
| API docs | http://localhost:8000/docs |
| MinIO console | http://localhost:9001 (`minioadmin` / `minioadmin`) |
| Flower (`make tools`) | http://localhost:5555 |
| OpenSearch Dashboards (`make tools`) | http://localhost:5601 |

Load a sample document and verify the whole path end to end:

```bash
make seed     # uploads a document, waits for it to index
make smoke    # checks health, dependencies, frameworks, and a live chat turn
```

Then ask the console something the sample document answers — *"what caused the
Sev-1 incidents last quarter?"* — and watch the Trace panel while the retriever
runs.

### Without Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
# Point POSTGRES_HOST / OPENSEARCH_HOST / REDIS_HOST at your own services.
alembic upgrade head
uvicorn app.main:app --reload

# Worker, separate terminal:
celery -A app.ingestion.celery_app.celery_app worker -Q ingest,default --loglevel=INFO

# UI, third terminal:
cd frontend && npm install && npm run dev     # http://localhost:5173
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  React console (Vite + nginx)                                            │
│  threads rail │ transcript + composer │ inspector: trace / config / files │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  SSE  (POST /api/v1/chat/stream)
┌───────────────────────────────▼──────────────────────────────────────────┐
│  FastAPI                                                                 │
│  middleware: correlation id · rate limit · error shaping                 │
│  routes: chat · conversations · runs · settings · files · search · audit │
│                              ChatService                                 │
│      resolve config → assemble memory → open run → stream → persist      │
└───┬────────────────────────────┬───────────────────────────┬─────────────┘
    │                            │                           │
┌───▼──────────────┐   ┌─────────▼──────────┐   ┌────────────▼─────────────┐
│ Agent runtime    │   │ Memory             │   │ Retrieval                │
│ ADK │ LangGraph  │   │ short: Postgres    │   │ BM25 ∥ kNN → RRF → rerank│
│ DeepAgents │ SDK │   │ long:  OpenSearch  │   │ OpenSearch               │
└───┬──────────────┘   └─────────┬──────────┘   └────────────┬─────────────┘
    │ 8 tools, each with a breaker and a timeout             │
    └────────────────────────────┴────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────────────┐
│ Postgres        OpenSearch        Redis + Celery        MinIO / S3       │
│ transcripts     chunks + memory   ingestion queue       uploaded files   │
│ runs, steps     hybrid indices    2 queues, retries     presigned URLs   │
│ settings, audit                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### The lifecycle of one turn

1. `POST /api/v1/chat/stream` arrives. Middleware assigns a request id and binds
   it to the logging context for everything that follows.
2. `ChatService.resolve_config` merges three sources, in precedence order:
   **request body → the user's saved settings → the defaults in `config.py`**.
3. The conversation is created or loaded. The user's message is written to
   Postgres *before* any model is called, so a crashed run still leaves a record
   of what was asked.
4. Memory is assembled: the last N turns from Postgres, the running summary, and
   — if enabled — semantically recalled long-term memories from OpenSearch.
5. An `agent_runs` row is opened and **committed immediately**. If the process
   dies mid-stream, the run is still visible with status `running` rather than
   vanishing.
6. The selected runtime streams `AgentEvent`s. The service forwards each one to
   the client as SSE while collecting text, citations, tool steps and usage.
7. When the stream closes, everything is persisted in a *fresh* session — the
   request session may have been rolled back by whatever failed.
8. `_post_turn` fires as a background task: roll the summary forward if the
   thread is long, distil durable facts into long-term memory. The user is
   already reading the answer by this point.

---

## The four runtimes

All four get the same five agents, the same eight tools, the same prompts and
the same memory block. They differ in how orchestration is expressed.

### LangGraph — explicit supervisor graph (default)

```
START → supervisor ─┬→ researcher ─┐
                    ├→ retriever  ─┴→ fan_in → supervisor
                    ├→ analyst ───────────────→ supervisor
                    ├→ compliance ────────────→ supervisor
                    └→ writer ────────────────→ END
```

The supervisor is a real node using structured output, not a prompt that decides
in free text. It returns a typed `Route` object. Structured routing is the
difference between a graph you can unit-test and one you can only observe.

`researcher` and `retriever` fan out in parallel and rejoin at `fan_in`, then
control returns to the supervisor for the next decision. Each specialist runs a
tool loop bounded at three passes — an unbounded loop here is how agent systems
burn a budget overnight.

**Use it when** you know the shape of the work and want it to be inspectable and
deterministic. This is the right default for most production work.

### Google ADK — declarative workflow agents (ADK 2.x)

```
SequentialAgent "agentmesh_pipeline"
  1. ParallelAgent "discovery"    → researcher ∥ retriever
  2. LlmAgent      "analyst"
  3. LoopAgent     "review_cycle" → compliance → writer   (max 2 iterations)
```

ADK's distinguishing idea is that orchestration is *composed*, not coded. State
moves between agents through `output_key`: each agent writes its result into
session state under a name, and the next agent's instruction interpolates it with
`{research_findings?}` templating. The `?` makes it optional, so a disabled agent
leaves a blank rather than an error.

The `LoopAgent` terminates early when compliance signals the draft passes,
instead of always burning both iterations.

Sessions persist through ADK 2.x's `DatabaseSessionService` pointed at the same
Postgres instance (in its own `adk` schema), with an in-memory fallback if that
is unavailable — degraded, not broken.

**Use it when** the pipeline is stable and you want it declared rather than
implemented. The declarative form is genuinely easier to review.

### LangChain DeepAgents — planning-first

The opposite philosophy. Instead of declaring the workflow, you give one capable
agent a planning tool, a virtual filesystem and a roster of subagents, and let it
decide. Our five specialists become declarative subagent specs; the main agent
gets the orchestrator instruction and the `task` tool that spawns them.

The virtual filesystem matters more than it sounds: long intermediate material
gets written to a file instead of carried in context, which is what keeps a
long research run from filling the window.

**Use it when** the shape of the work is not known in advance — open-ended
research, exploratory analysis. It is less predictable than the graph, which is
the point.

### Claude Agent SDK — Anthropic's harness

Uses `ClaudeSDKClient` with `ClaudeAgentOptions`, and exposes our tools through
an **in-process MCP server** (`create_sdk_mcp_server`). In-process means no
subprocess and no IPC — a tool call lands directly in the FastAPI event loop.

The five specialists become programmatic subagents via the `agents` option, each
with its own prompt and tool allowlist.

This runtime talks to Claude models specifically. If you have an OpenAI or Gemini
model selected, it says so and stops rather than silently substituting — a
quietly swapped model is a worse outcome than a clear error.

**Use it when** you are on Claude models and want Anthropic's own context
management, compaction and permission model rather than reimplementing them.

### Choosing between them

| | LangGraph | Google ADK | DeepAgents | Claude SDK |
|---|---|---|---|---|
| Control flow | explicit graph | declarative composition | model-decided | model-decided |
| Predictability | high | high | moderate | moderate |
| Parallelism | fan-out edges | `ParallelAgent` | subagent spawning | subagent spawning |
| Best for | known workflows | stable pipelines | open-ended research | Claude-native agents |
| Providers | all three | all three (LiteLLM) | all three | Anthropic only |

---

## The five agents and their tools

Prompts live in one file — `app/agents/definitions.py` — and every framework
reads from it. A wording change lands in all four at once, and a behavioural
regression is attributable to a single diff.

| Agent | Job | Tools |
|---|---|---|
| **Orchestrator** | Plans, routes, merges, owns the final answer | delegation |
| **Researcher** | External and corpus-level discovery | `web_search`, `corpus_overview` |
| **Retriever** | Hybrid RAG over the user's documents, returns cited passages | `hybrid_search`, `fetch_document_chunk` |
| **Analyst** | Arithmetic and quantitative reasoning | `calculator`, `table_stats` |
| **Compliance** | PII, policy and unsupported-claim review | `pii_scan`, `policy_lookup` |
| **Writer** | Final composition with citations intact | — |

The routing rules are in the orchestrator prompt, and the first one is the one
that matters most in practice:

> A greeting or a trivial question needs no delegation. Answer it and stop.
> Spinning up five agents for 'hi' is a bug, not thoroughness.

Tools are plain async functions in `app/agents/tools/core.py`. The adapters in
`adapters.py` wrap them into LangChain `StructuredTool`s, ADK `FunctionTool`s or
Claude SDK MCP tools — the logic is written once. Every wrapper adds a per-tool
circuit breaker, a timeout and a structured log line, so a tool that starts
failing degrades into a recoverable error message the agent can react to rather
than an exception that kills the run.

Turn agents on and off per user in the Config panel. The mesh requires at least
one.

---

## Memory

Two stores doing two different jobs.

### Short-term — Postgres, the record

Everything lands here: every message, every agent step, every tool call, with a
JSONB `metadata` column carrying citations, routing decisions, usage and the
request id. A GIN index makes that column queryable.

The prompt window is a **view** over this, not the storage itself
(`AGENT_SHORT_TERM_WINDOW`, default 20 turns). That distinction is what lets you
widen the window, replay a run, or audit what an agent actually did — none of
which is possible if history only ever lived in a framework's session object.

When a thread outgrows the window, older turns are folded into a running summary
stored on the conversation row. Summarisation runs after the turn, never on the
request path.

### Long-term — OpenSearch, the distillate

After a turn, a separate LLM pass extracts durable facts — stated preferences,
stable context, decisions, constraints — and indexes them with embeddings. In a
later conversation that shares no keywords, `recall()` finds them semantically.

Two rules govern this:

1. **It runs off the request path.** A user never waits on memory writing.
2. **Most turns extract nothing.** The extraction prompt says so explicitly. A
   memory store that saves everything is one nobody can retrieve from.

Tenant isolation is a query constraint, not a post-filter: `user_id` sits inside
the kNN filter clause, so the ANN search never traverses another tenant's
vectors.

`LongTermMemory.forget()` supports deletion by memory id or by whole
conversation, for the right-to-be-forgotten case.

---

## Hybrid search

Two independent queries — BM25 and kNN — fused by **Reciprocal Rank Fusion**:

```
score(d) = Σ  1 / (k + rank_i(d))          k = 60 by default
```

RRF over weighted score normalisation, for a specific reason. BM25 scores are
unbounded and corpus-relative — the same query against the same document scores
differently after you ingest a hundred more documents, because IDF moved. Cosine
similarity is bounded and absolute. Normalising them onto a shared scale gives
you a blend whose effective weighting drifts as the corpus grows, and it drifts
*silently*. You find out as "retrieval got worse this quarter" with no single
change to blame.

RRF looks only at ranks. Rank 1 in either leg contributes the same today and
after ten thousand more documents. The cost is that it discards magnitude — two
documents adjacent in rank contribute equally even if their raw scores differ by
an order of magnitude. For a growing corpus that is the right trade. If your
corpus is fixed and you have relevance judgements to tune against, weighted
fusion can beat it.

The two legs run concurrently and either may fail. If embedding is unavailable,
retrieval degrades to lexical-only with a logged warning rather than failing the
answer. Only when both legs fail do we raise.

Optional cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`) runs on the fused
head. Off by default — it roughly doubles p95 retrieval latency.

Debug retrieval directly, outside any agent:

```bash
curl -sS -X POST localhost:8000/api/v1/search \
  -H 'X-User-ID: demo-user' -H 'Content-Type: application/json' \
  -d '{"query":"revenue growth drivers","top_k":5}' | python3 -m json.tool
```

The response includes each hit's `bm25_rank` and `knn_rank`, so you can see
which leg found what.

---

## Resilience: retry and circuit breaking

`app/core/resilience.py`. Hand-rolled rather than pulled from a library, for
three reasons.

**Half-open probes are capped.** Most small breaker libraries release every
waiting caller the moment the reset timeout expires, so a recovering dependency
gets hit by the entire backlog and immediately fails again. Ours allows
`half_open_max_calls` concurrent probes and requires `success_threshold`
consecutive successes before closing.

**Not every error trips the circuit.** `is_retryable()` decides. A 400 from a
provider means *our* payload is wrong — retrying is pointless, and tripping the
breaker on it would take down a healthy dependency because of our own bug. Only
timeouts, connection failures, 429s and 5xx count. This is the detail most
implementations get wrong; there is a test that exists solely to hold that line.

**It is introspectable.** `CircuitBreaker.snapshot()` feeds `/api/v1/health` and
the status bar in the UI. When a breaker opens, an operator sees which one, for
how long, and with what last error, without reading logs.

### Composition order

`with_resilience` wraps **timeout → breaker → retry**, deliberately:

- Timeout innermost, so each attempt gets its own budget instead of sharing one
  across the whole retry sequence.
- Breaker inside the retry loop, so a tripped circuit short-circuits every
  attempt immediately rather than being retried around.

Reverse these and you get a retry loop that spends its entire budget hammering a
dependency already known to be down.

### What has a breaker

`llm.openai`, `llm.anthropic`, `llm.google`, `opensearch`, `object_storage`,
`embeddings`, and one per tool (`tool.hybrid_search`, `tool.web_search`, …).

Retry is exponential backoff with full jitter — `0.5s → 1s → 2s → 4s` plus a
random component, capped at `RESILIENCE_MAX_BACKOFF_SECONDS`. Jitter matters:
without it, everything that failed together retries together.

```bash
curl -s localhost:8000/api/v1/health | python3 -m json.tool | head -40
```

---

## Document ingestion

```
upload → checksum → object storage → Redis queue → Celery worker
       → parse → chunk → embed (batched) → bulk index → status to Postgres
```

The request path does the minimum: checksum the bytes, store them, write a row,
enqueue. A `202` means *accepted*, not *searchable*. The client polls status —
and the console only polls while something is actually mid-ingestion.

**Formats:** PDF (with OCR fallback for scans via tesseract), DOCX, XLSX, CSV,
HTML, JSON, Markdown, plain text. Every parser degrades to text decoding rather
than raising; a partially readable document beats a failed job.

**Chunking** is recursive on structural boundaries (`\n## `, `\n# `, paragraph,
line, sentence) with overlap, and it is page-aware — that is what lets citations
carry a page number.

**Idempotency is the whole design.** Chunk ids are deterministic:

```python
"_id": f"{document_id}:{chunk.index}"
```

That is what makes `acks_late=True` + `reject_on_worker_lost=True` safe. A task
whose worker dies is redelivered and overwrites the same documents. Without
deterministic ids, every interrupted document would duplicate — and duplicates
in a RAG index are worse than missing content, because they crowd out other
sources in the top-k.

Other worker settings worth knowing: `worker_prefetch_multiplier=1` (these tasks
run for minutes; a worker that prefetches four leaves three idle behind a slow
one) and `worker_max_tasks_per_child=50` (PDF parsers leak; recycling is cheaper
than hunting it down).

Retries use Celery's `autoretry_for` with backoff and jitter, four attempts.
Progress is written to Postgres, not just Celery's result backend, so the UI
shows ingestion state without talking to Redis.

Scale ingestion independently of the API:

```bash
make scale-workers n=4
```

---

## Streaming

SSE, not websockets. The traffic is one-directional — the client posts and then
reads until the run ends. A websocket would add lifecycle management and proxy
configuration for no gain.

SSE has one operational trap that accounts for most "the UI hangs" reports:
**intermediate proxies buffer it**. Three things must line up.

1. The response sets `X-Accel-Buffering: no` (`app/api/v1/chat.py`).
2. nginx sets `proxy_buffering off` with a long `proxy_read_timeout`
   (`frontend/nginx.conf`, `infra/nginx/agentmesh.conf`).
3. A heartbeat every 15 seconds keeps idle intermediaries from closing the
   connection during a long tool call.

The client uses `fetch` plus a stream reader rather than `EventSource`, because
`EventSource` cannot send a POST body or custom headers.

Each frame is one JSON event:

```
data: {"type":"plan","agent":"orchestrator","data":{"plan":["retrieve","analyse","write"]}}
data: {"type":"tool_call","agent":"retriever","data":{"tool":"hybrid_search","input":{...}}}
data: {"type":"token","agent":"writer","data":{"text":"Revenue grew "}}
data: {"type":"run_finished","data":{"duration_ms":8421,"total_tokens":3902}}
data: [DONE]
```

---

## The UI

Three panes: a threads rail, the transcript with its composer, and an inspector
that switches between **Trace**, **Config** and **Files**.

The visual direction is an instrument panel rather than a chat toy. Charcoal
chassis, signal amber for anything the operator acts on, and cyan reserved
strictly for agent telemetry — so the eye learns that cyan means *a machine did
something*. Monospace for every label and control; a serif only for the
assistant's prose, because that is the one thing on screen meant to be read
rather than scanned.

**Trace** shows the run live: hand-offs, tool calls with their arguments, tool
results with durations, and the final token and timing totals. This is the panel
that makes a multi-agent system debuggable instead of mysterious.

**Config** exposes every runtime knob — framework (with install status per
framework), provider, model, temperature, max tokens, which specialists are
active, and the memory toggles. Everything here maps to a field the backend
already understands, so nothing in this panel needs a server change to take
effect. Settings persist per user.

**Files** handles drag-and-drop upload, shows live ingestion status with chunk
and page counts, and lets you *scope a turn to specific documents* — the
retriever then searches only those, which is the fastest way to get a precise
answer out of a large corpus.

The status bar carries overall health and, when a circuit breaker opens, names
it. A degraded dependency is visible without opening a terminal.

---

## API reference

Base path `/api/v1`. Identity comes from the `X-User-ID` header (see
[Running it in production](#running-it-in-production)).

### Chat

| Method | Path | Notes |
|---|---|---|
| `POST` | `/chat/stream` | SSE. One JSON event per frame, terminated by `[DONE]` |
| `POST` | `/chat` | Non-streaming. For scripts and eval harnesses |
| `GET` | `/frameworks` | The four runtimes with install status, plus the agent roster |

```bash
curl -N -X POST localhost:8000/api/v1/chat/stream \
  -H 'X-User-ID: demo-user' -H 'Content-Type: application/json' \
  -d '{
        "message": "What drove revenue growth last quarter?",
        "framework": "langgraph",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "enabled_agents": ["retriever", "analyst", "writer"]
      }'
```

Every field except `message` is optional and overrides the stored settings for
that one call.

### Conversations and runs

| Method | Path | Notes |
|---|---|---|
| `GET` | `/conversations` | Paginated |
| `GET` | `/conversations/{id}` | With full message history |
| `PATCH` | `/conversations/{id}` | Rename, archive, set a system prompt |
| `DELETE` | `/conversations/{id}` | Cascades to messages, runs and steps |
| `GET` | `/conversations/{id}/runs` | Every orchestrator run in the thread |
| `GET` | `/runs/{id}` | One run with every agent step — the replay endpoint |

### Settings

| Method | Path | Notes |
|---|---|---|
| `GET` | `/settings` | The caller's settings, falling back to `config.py` |
| `PUT` | `/settings` | Persist |
| `GET` | `/settings/options` | Frameworks, agents, model catalogue and defaults in one call |

### Files and search

| Method | Path | Notes |
|---|---|---|
| `POST` | `/files` | Multipart upload. `202` and a Celery task id |
| `GET` | `/files` | With ingestion status, chunk and page counts |
| `GET` | `/files/{id}/download` | Presigned URL |
| `POST` | `/files/{id}/reingest` | Re-run the pipeline |
| `DELETE` | `/files/{id}` | Removes the object, the row and every chunk |
| `POST` | `/search` | Raw hybrid search, no agent involved |

### Audit and health

| Method | Path | Notes |
|---|---|---|
| `GET` | `/audit` | Filter by action, resource, outcome, time range |
| `GET` | `/health/live` | Liveness. Touches nothing |
| `GET` | `/health/ready` | Readiness. `503` when a dependency is down |
| `GET` | `/health` | Full detail: dependencies, breaker states, framework availability |

Three health endpoints because Kubernetes asks three different questions.

Interactive docs at `/docs`.

---

## Configuration reference

Everything is environment-driven through `app/config.py`. Nothing else in the
codebase reads `os.environ`, so every knob is typed, validated and documented in
one place.

### Agent defaults

| Variable | Default | Notes |
|---|---|---|
| `AGENT_FRAMEWORK` | `langgraph` | `langgraph`, `google_adk`, `deepagents`, `claude_agent_sdk` |
| `AGENT_PROVIDER` | `anthropic` | `anthropic`, `openai`, `google` |
| `AGENT_MODEL` | `claude-sonnet-4-6` | Must exist for the provider |
| `AGENT_TEMPERATURE` | `0.2` | Above ~0.5 the writer paraphrases sources instead of citing them |
| `AGENT_MAX_TOKENS` | `4096` | |
| `AGENT_MAX_ORCHESTRATOR_STEPS` | `12` | Hard ceiling on routing iterations |
| `AGENT_SHORT_TERM_WINDOW` | `20` | Turns replayed into the prompt |
| `AGENT_LONG_TERM_TOP_K` | `5` | Memories recalled per turn |
| `AGENT_ENABLE_LONG_TERM_MEMORY` | `true` | |

These are *defaults*. A user's saved settings override them; a request body
overrides both.

### Retrieval

| Variable | Default | Notes |
|---|---|---|
| `OPENSEARCH_EMBEDDING_DIM` | `1536` | Must match the embedding model. Changing it needs a reindex |
| `OPENSEARCH_BM25_TOP_K` | `50` | Candidates from the lexical leg |
| `OPENSEARCH_KNN_TOP_K` | `50` | Candidates from the vector leg |
| `OPENSEARCH_RRF_K` | `60` | Lower makes top ranks dominate more sharply |
| `OPENSEARCH_FINAL_TOP_K` | `8` | Passages handed to the agent |

### Resilience

| Variable | Default | Notes |
|---|---|---|
| `RESILIENCE_MAX_ATTEMPTS` | `4` | Includes the first try |
| `RESILIENCE_INITIAL_BACKOFF_SECONDS` | `0.5` | Doubles, with jitter |
| `RESILIENCE_FAILURE_THRESHOLD` | `5` | Consecutive failures before opening |
| `RESILIENCE_SUCCESS_THRESHOLD` | `2` | Consecutive successes before closing |
| `RESILIENCE_BREAKER_RESET_TIMEOUT_SECONDS` | `30` | Open → half-open |
| `RESILIENCE_LLM_TIMEOUT_SECONDS` | `120` | Per attempt |
| `RESILIENCE_TOOL_TIMEOUT_SECONDS` | `30` | Per attempt |

### Ingestion

| Variable | Default | Notes |
|---|---|---|
| `INGESTION_CHUNK_SIZE` | `1200` | Characters |
| `INGESTION_CHUNK_OVERLAP` | `180` | Boundary loss is where RAG quietly fails |
| `INGESTION_EMBEDDING_MODEL` | `text-embedding-3-small` | Changing it requires a reindex |
| `INGESTION_EMBEDDING_BATCH_SIZE` | `64` | |

Full list in `.env.example`.

---

## Project layout

```
agentmesh/
├── backend/
│   ├── app/
│   │   ├── config.py             # every knob, typed and validated
│   │   ├── main.py               # app factory, lifespan, middleware
│   │   ├── agents/
│   │   │   ├── base.py           # ★ AgentEvent / RunContext / AgentRuntime
│   │   │   ├── definitions.py    # the five agents, prompts written once
│   │   │   ├── registry.py       # framework selection + install probe
│   │   │   ├── service.py        # ChatService: the orchestration seam
│   │   │   ├── frameworks/       # one adapter per runtime
│   │   │   └── tools/            # neutral tools + per-framework wrappers
│   │   ├── core/
│   │   │   ├── resilience.py     # ★ breaker, retry, bulkhead
│   │   │   ├── middleware.py     # correlation, rate limit, error shaping
│   │   │   └── logging.py        # structlog with request context
│   │   ├── db/                   # models, session, repositories
│   │   ├── memory/               # short_term (PG) + long_term (OpenSearch)
│   │   ├── search/               # client, index mappings, hybrid + RRF
│   │   ├── ingestion/            # celery app, parsers, chunking, tasks
│   │   ├── storage/              # S3 / MinIO
│   │   ├── api/v1/               # routes
│   │   └── schemas/              # Pydantic contracts
│   ├── alembic/                  # migrations
│   └── tests/
├── frontend/
│   └── src/
│       ├── App.jsx               # three-pane shell
│       ├── hooks/useChat.js      # SSE state: prose and telemetry kept apart
│       ├── lib/api.js            # fetch-based SSE reader
│       └── components/           # Transcript, Composer, Settings, Trace, Files
├── infra/                        # postgres init, opensearch, nginx
├── scripts/                      # seed, smoke, reindex
├── docs/architecture.md          # the longer reasoning
├── docker-compose.yml
└── Makefile
```

The two files marked ★ are where the design actually lives. If you read only
two, read those.

---

## Running it in production

The compose file runs a complete stack on a laptop. Several things in it are
laptop choices, and shipping them unchanged would be a mistake.

**Authentication is a seam, not an implementation.** `app/api/deps.py` reads
`X-User-ID`. Everything downstream takes a user id, so dropping in JWT
verification or OIDC introspection touches one file — but until you do, the API
trusts a header. Do this first.

**Turn the OpenSearch security plugin back on.** `DISABLE_SECURITY_PLUGIN=true`
is set for local convenience. `infra/opensearch/opensearch.yml` is the starting
point for undoing it, with real certificates.

**Move rate limiting into Redis.** The current sliding window is in-process,
which is correct for one replica and wrong for several. The middleware interface
does not change.

**Scale the tiers separately.** The API is IO-bound and scales on request
concurrency. Ingestion workers are embedding-throughput-bound and scale on queue
depth — that is why they are a separate service on a separate queue. OpenSearch
needs the memory: HNSW graphs are resident, and
`knn.memory.circuit_breaker.limit` caps how much heap they may take.

**Set `LOG_FORMAT=json`.** Every line carries `request_id`, `conversation_id` and
`user_id` from contextvars, which is what makes a multi-agent trace reconstructable
after the fact. OTLP export is wired behind `OTEL_ENABLED`.

**Back up Postgres, snapshot OpenSearch.** Postgres is the system of record;
OpenSearch is derived and can be rebuilt by re-ingesting, but rebuilding costs
real money in embedding calls.

### What this deliberately does not do

- **No cost accounting.** Token counts are recorded; dollars are not.
  `Conversation.total_cost_usd` exists and is always `0.0`.
- **`enabled_agents` gates which specialists exist**, not a per-agent token
  budget. A pathological question can still consume `max_orchestrator_steps`.
- **Reranking is off by default** and roughly doubles p95 retrieval latency.
  Measure before turning it on in a latency-sensitive path.
- **The Claude Agent SDK path runs Anthropic models only.** It errors clearly
  rather than substituting.

---

## Troubleshooting

**The UI hangs with no tokens appearing.** SSE is being buffered. Check
`proxy_buffering off` in whatever proxy sits in front, and confirm
`X-Accel-Buffering: no` survives to the client. This is the most common failure
and it is always the proxy.

**`framework_unavailable` from a runtime.** The Python package is not in the
image. `GET /api/v1/frameworks` reports install status per framework and says
which package is missing.

**Uploads stay `queued` forever.** The worker is not consuming. Check
`make logs-worker`, and confirm it is listening on the `ingest` queue —
ingestion tasks are routed there specifically.

**Ingestion reaches `failed` with "No extractable text".** A scanned PDF with no
text layer. OCR is installed in the image but is slow and needs a readable scan;
check the worker logs for `ocr_unavailable`.

**Retrieval returns nothing after changing the embedding model.** A `knn_vector`
dimension cannot change in place. Run `make reindex`, restart the backend, then
re-ingest.

**A circuit is open.** `GET /api/v1/health` names it, tells you how long it has
been open and shows the last error. It closes itself after
`RESILIENCE_BREAKER_RESET_TIMEOUT_SECONDS` and two successful probes. If it
reopens immediately, the dependency is genuinely down — look at `last_error`.

**OpenSearch will not start.** Almost always memory. It wants 1 GB of heap plus
overhead; give Docker at least 4 GB. Check `docker compose logs opensearch` for
`max virtual memory areas vm.max_map_count [65530] is too low` and raise it.

**Chat returns empty answers.** No provider key. `make smoke` says so explicitly.

---

## Extending it

### Add a fifth framework

Implement `AgentRuntime` — one method, `stream(ctx) -> AsyncIterator[AgentEvent]`
— translate the framework's events into our vocabulary, register it in
`app/agents/registry.py` and add a value to the `AgentFramework` enum. The API,
the database, the UI and the tests need no changes. That is the entire point of
the design.

### Add a tool

Write an async function in `app/agents/tools/core.py` with a typed signature and
a docstring — the docstring *is* the model-facing description. Register it in
`TOOL_REGISTRY` and `TOOL_SCHEMAS`, then list it on whichever agent should have
it in `definitions.py`. All four adapters pick it up automatically, breaker and
timeout included.

### Add an agent

Add an `AgentSpec` to `definitions.py`. It appears in `/settings/options`, in the
UI toggles and in every framework. The ADK and LangGraph adapters need a line
each to place it in their topology; DeepAgents and the Claude SDK pick it up
from the roster with no change.

### Add a model provider

Extend `ModelProvider` and `MODEL_CATALOGUE` in `config.py`, then add the
construction branch in `app/llm/registry.py`. The UI reads the catalogue over
the API, so a new model appears in the picker without a frontend build.

---

## Tests

```bash
make test          # in the container
make test-local    # on the host
make lint          # ruff
```

The suite concentrates on the parts that only run when something is already
going wrong — breaker state transitions, retry classification, RRF fusion, chunk
boundaries — because that is where a bug surfaces at the worst possible moment.
`test_breaker_ignores_non_retryable_errors` exists specifically to hold the line
that a `400` must never trip a circuit.
