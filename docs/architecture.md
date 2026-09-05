# Architecture notes

Longer-form reasoning behind the decisions the README only states. Written for
whoever inherits this and wonders why it looks like this.

---

## The central abstraction: one event stream, four runtimes

Every framework here has a different execution model. ADK emits `Event` objects
from a `Runner`. LangGraph emits state deltas per node. DeepAgents emits
LangChain message chunks. The Claude Agent SDK emits typed message blocks.

If any of that leaked upward, the API layer would need four code paths, the
persistence layer would need four schemas, and the React client would need four
renderers. Adding a fifth framework would be a rewrite.

So `app/agents/base.py` defines a single `AgentEvent` vocabulary — `plan`,
`agent_started`, `tool_call`, `tool_result`, `token`, `citation`, `handoff`,
`usage`, `error`, `run_finished` — and each adapter's only job is translation.
Everything above the adapter sees one stream.

The practical test of whether this abstraction is real: you can switch runtimes
mid-conversation and the transcript, the trace panel, the `agent_steps` rows and
the citation markers all keep working. That works because history lives in
Postgres in a framework-neutral shape, not inside any framework's session store.

### Where it leaks, honestly

Two places.

The Claude Agent SDK maintains its own session and context compaction. We replay
our short-term window into the prompt rather than handing it our session, which
means on a very long thread the SDK is doing its own compaction on top of ours.
It works, but it is not elegant.

ADK's `output_key` state passing is genuinely declarative in a way the others
are not. The `{research_findings?}` templating in an instruction has no direct
equivalent in the LangGraph adapter, where we build the same context by string
assembly in `_run_specialist`. Same result, more code.

---

## Why RRF and not weighted score fusion

The obvious way to combine BM25 and vector results is to normalise both scores
to [0,1] and take a weighted sum. We do not, for a specific reason.

BM25 scores are unbounded and corpus-relative. The same query against the same
document scores differently after you ingest a hundred more documents, because
IDF moved. Cosine similarity is bounded and absolute. Normalising them onto a
shared scale produces a blend whose effective weighting drifts as the corpus
grows — and it drifts silently, because nothing errors. You discover it as
"retrieval got worse over the last quarter" with no single change to blame.

Reciprocal Rank Fusion looks only at ranks:

```
score(d) = Σ  1 / (k + rank_i(d))
```

Rank 1 in either leg contributes the same amount today and after ten thousand
more documents. `k` (default 60) controls how sharply top ranks dominate — lower
`k` makes the head steeper.

The cost is that RRF discards magnitude. A document that BM25 scores at 40.0 and
one it scores at 4.0 contribute identically if they are adjacent in rank. That is
the trade, and for a corpus that grows it is the right one. If your corpus is
fixed and you have relevance judgements to tune against, weighted fusion can beat
it.

## Why the retrieval legs run in parallel with `return_exceptions=True`

`hybrid_search` gathers both legs concurrently and tolerates either failing. If
the embedding provider is down, we still return BM25 results and the agent still
answers, with a logged warning. If OpenSearch is up but the kNN query fails on a
mapping problem, lexical still works.

Only when both legs fail do we raise. A degraded answer beats no answer, and the
alternative — coupling retrieval availability to embedding-provider availability —
means one vendor's incident takes down search.

---

## Circuit breakers: why hand-rolled

There are libraries. We wrote our own (`app/core/resilience.py`) for three
reasons.

**Async-native half-open semantics.** Most small breaker libraries let every
waiting caller through when the reset timeout expires, so a recovering
dependency gets slammed by the entire backlog and immediately fails again. Ours
caps concurrent half-open probes (`half_open_max_calls`) and requires
`success_threshold` consecutive successes before closing.

**Selective tripping.** `is_retryable()` decides what counts as a dependency
failure. A 400 from a provider means our payload is wrong; retrying is pointless
and tripping the circuit on it would take down a working dependency because of
our own bug. Only timeouts, connection errors, 429s and 5xx count. This is the
detail most implementations get wrong, and `test_breaker_ignores_non_retryable_errors`
exists specifically to hold that line.

**Introspection.** `CircuitBreaker.snapshot()` feeds `/api/v1/health` and the
status bar in the UI. When a breaker opens, an operator sees which one, for how
long, and with what last error, without reading logs.

### Composition order

`with_resilience` wraps timeout → breaker → retry, and the order is deliberate:

- Timeout innermost, so each attempt gets its own budget rather than sharing one
  across the whole retry sequence.
- Breaker inside the retry loop, so a tripped circuit is observed on every
  attempt and short-circuits immediately instead of being retried around.

Reversing these gives you a retry loop that spends its whole budget on a
dependency that is already known to be down.

---

## Memory: two stores, two jobs

**Postgres is the record.** Every message, every agent step, every tool call,
with a JSONB metadata column. The prompt window is a *view* over it
(`ShortTermMemory.window()`), which means we can widen the window, replay a run,
or audit what an agent actually did — none of which is possible if the
transcript only ever lived in a framework's session object.

**OpenSearch holds the distillate.** After a turn completes, a separate LLM pass
extracts durable facts and writes them with embeddings. In a later conversation
sharing no keywords, `recall()` finds them semantically.

Two rules govern this:

1. **Extraction runs off the request path.** `_post_turn` is fired as a task
   after the stream closes. A user never waits on memory writing.
2. **Most turns extract nothing.** The prompt says so explicitly. A memory store
   that saves everything is a memory store nobody can retrieve from.

Tenant isolation is a query constraint, not a post-filter: `user_id` goes inside
the kNN filter clause, so the ANN search never traverses another tenant's
vectors.

---

## Ingestion: why idempotency is the whole design

The Celery config uses `acks_late=True` with `reject_on_worker_lost=True`. A task
whose worker dies is redelivered rather than lost. That is only safe because
chunk ids are deterministic:

```python
"_id": f"{document_id}:{chunk.index}"
```

A redelivered task overwrites the same documents. Without this, `acks_late` would
duplicate every chunk of every interrupted document, and duplicates in a RAG
index are worse than missing content — they crowd out other sources in the top-k.

Other choices worth naming:

- `worker_prefetch_multiplier=1`: these tasks run for minutes. A worker that
  prefetches four of them leaves three sitting idle behind a slow one.
- `worker_max_tasks_per_child=50`: PDF parsers leak. Recycling the process is
  cheaper than finding the leak.
- Progress is written to Postgres, not just Celery's result backend, so the UI
  can show ingestion state without talking to Redis.

---

## Streaming: SSE, not websockets

The traffic is one-directional. The client posts a request and reads events until
the run ends. A websocket would add connection lifecycle management, a heartbeat
protocol, and proxy configuration for no gain.

SSE has one operational trap, and it accounts for most "the UI hangs" reports:
**intermediate proxies buffer it**. Three things must line up:

1. The response sets `X-Accel-Buffering: no` (`app/api/v1/chat.py`).
2. nginx sets `proxy_buffering off` and a long `proxy_read_timeout`
   (`frontend/nginx.conf` and `infra/nginx/agentmesh.conf`).
3. The server emits a heartbeat every 15s so idle intermediaries do not close a
   connection during a long tool call.

On the client we use `fetch` plus a stream reader rather than `EventSource`,
because `EventSource` cannot send a POST body or custom headers.

---

## What this does not do

Stated plainly, because a README that only lists strengths is not useful to
whoever has to run this.

- **Authentication is a seam, not an implementation.** `app/api/deps.py` reads
  `X-User-ID`. Everything downstream takes a user id, so dropping in JWT
  verification touches one file — but until you do, the API trusts a header.
- **Rate limiting is in-process.** Fine for one replica. With more than one, move
  the sliding window into Redis; the middleware interface does not change.
- **No cost accounting.** Token counts are recorded; dollar cost is not
  calculated. `Conversation.total_cost_usd` exists and is always 0.0.
- **The security plugin is off in local compose.** Deliberate for a laptop,
  wrong for anything shared. `infra/opensearch/opensearch.yml` is the starting
  point for turning it back on.
- **`enabled_agents` gates which specialists exist, not a per-agent budget.** A
  pathological question can still burn `max_orchestrator_steps` on routing.
- **Cross-encoder reranking is off by default** and roughly doubles p95 retrieval
  latency when on. Measure before enabling it in a latency-sensitive path.
