# Refundry UI — Node.js Dashboard

A small **Node.js (Express)** web app that puts a browser dashboard in front of the
Refundry refund-resolution network. It is a thin layer: it serves a single-page UI and
**proxies every API call through to the Python FastAPI gateway** on port `8080`. No refund
logic lives here — exactly like the gateway, the UI decides nothing.

```
  Browser ──▶ Node.js UI server (:3000) ──▶ Refundry gateway (FastAPI, :8080)
              serves the dashboard           A2A ──▶ 6 agents ──▶ MCP ──▶ 7 servers
              proxies /api + /health
```

## What the dashboard gives you

| Tab | What it does | Gateway endpoints used |
|---|---|---|
| **File a claim** | Submit a refund claim and watch the agent mesh resolve it live, with a human-approval step when a signature is required | `POST /api/v1/refunds`, `GET …/stream` (SSE), `POST …/approve` |
| **Cases** | Every case, drill into the full protocol trail (every A2A + MCP exchange) | `GET /api/v1/cases`, `GET /api/v1/trail/{case}` |
| **Ledger** | Every refund that was actually posted | `GET /api/v1/ledger` |
| **Network** | Live health of all 15 services, every A2A Agent Card, every MCP server | `GET /api/v1/doctor`, `/agents`, `/servers` |

The header shows live gateway health (online / offline, reasoning mode, Jev backend) and a
**orchestrator selector** (see below).

---

## Choosing the orchestrator engine

The header has an **orchestrator** dropdown. The Arbiter's process is a graph of nodes and
edges; *what* each node does is fixed, but *how* the graph is walked is pluggable. Pick any
of three engines — they run the **same six agents** and produce the **same refund outcome**:

| Option | Engine | Needs |
|---|---|---|
| **deterministic · jev:local** | The project's own ~90-line state-graph engine (default) | — |
| **LangGraph** | A real LangGraph `StateGraph` with dynamic `Command` routing and a conditional entry point | `langgraph` |
| **Google ADK** | A real Google ADK custom workflow agent driven by the ADK `Runner` | `google-adk` |

Your choice is **saved in SQLite** (the `app_settings` table) via `PUT /api/v1/orchestrator`,
so it survives page reloads, gateway restarts, and even `make seed`. (Postgres later changes
nothing — the store swap is transparent.) Each case records which engine resolved it, shown
in the **Live case** panel and the audit trail; a case started on one engine always *resumes*
on that same engine, even if you switch the global selection mid-approval.

If an engine's optional package is not installed, its option appears disabled as
`… (not installed)` and the app falls back to the deterministic engine. Install all three
with `make install` (they are listed in `requirements.txt`) or:

```bash
.venv/bin/pip install langgraph google-adk
```

---

## Prerequisites

- **Node.js ≥ 18** (tested on Node 22) and npm
- The **Refundry backend running** — the gateway must be up on `http://127.0.0.1:8080`
- Optional, for the LangGraph / Google ADK engines: `pip install langgraph google-adk`

---

## Start it end to end

You need **two processes**: the Python backend and the Node.js UI.

### 1 — Start the Refundry backend (terminal 1)

From the repository root:

```bash
make install      # one-time: venv + Python deps
make run          # starts all 15 services (7 MCP, 7 agents, 1 gateway on :8080)
```

Leave that running. Confirm it is healthy:

```bash
curl -s http://127.0.0.1:8080/api/v1/health
```

### 2 — Start the Node.js UI (terminal 2)

```bash
cd ui
npm install       # one-time: installs express + http-proxy-middleware
npm start         # serves the dashboard on http://127.0.0.1:3000
```

Then open **<http://127.0.0.1:3000>** in your browser.

That's it. File the sample claim, watch the timeline stream in, and approve the
$1,284.00 spend when the dashboard stops and asks you to sign.

---

## Try the full flow

1. Open <http://127.0.0.1:3000> — the header should read **online**.
2. (Optional) Pick an engine in the **orchestrator** dropdown — deterministic, LangGraph,
   or Google ADK. The choice is saved to SQLite immediately.
3. On **File a claim**, keep the pre-filled example and click **Submit claim**.
4. The **Live case** panel streams the agents' work in real time (SSE) and shows which
   **Orchestrator** resolved the case.
5. The case stops at **✍︎ Approval required** — `$1,284.00` needs a named approver.
6. Click **Approve spend**. The case resumes (on the same engine it started on) and
   resolves; the refund posts.
7. Check the **Ledger** and **Cases → trail →** tabs to see the result and the full
   protocol trace, including the `orchestrator.selected` entry.

Re-run with a different engine to confirm the outcome is identical — only the orchestration
mechanics change.

---

## Configuration

The UI reads two environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `3000` | Port the Node.js UI listens on |
| `GATEWAY_URL` | `http://127.0.0.1:8080` | Where the Refundry FastAPI gateway lives |

Examples:

```bash
# serve the UI on a different port
PORT=4000 npm start

# point the UI at a gateway on another host
GATEWAY_URL=http://10.0.0.5:8080 npm start
```

For live-reload during development:

```bash
npm run dev       # node --watch server.js
```

---

## Files

```
ui/
  package.json          Node project + dependencies (express, http-proxy-middleware)
  server.js             Express server: serves /public and proxies /api + /health
  public/
    index.html          the dashboard markup
    styles.css          dark dashboard theme
    app.js              all the UI logic (fetch, SSE, approvals, tables)
```

---

## Troubleshooting

- **Header shows "gateway offline" / 502 errors** — the backend isn't up. Run `make run`
  from the repo root and confirm `curl http://127.0.0.1:8080/api/v1/health` responds.
- **Port 3000 already in use** — start with `PORT=4000 npm start`.
- **Nothing streams in the timeline** — the case may have resolved instantly (no approval
  needed). Check the **Cases** tab; the trail is always recorded.
- **`npm start` fails with a module error** — run `npm install` inside `ui/` first.
