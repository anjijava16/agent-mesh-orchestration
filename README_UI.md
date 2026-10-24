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

The header shows live gateway health (online / offline, reasoning mode, Jev backend).

---

## Prerequisites

- **Node.js ≥ 18** (tested on Node 22) and npm
- The **Refundry backend running** — the gateway must be up on `http://127.0.0.1:8080`

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
2. On **File a claim**, keep the pre-filled example and click **Submit claim**.
3. The **Live case** panel streams the agents' work in real time (SSE).
4. The case stops at **✍︎ Approval required** — `$1,284.00` needs a named approver.
5. Click **Approve spend**. The case resumes and resolves; the refund posts.
6. Check the **Ledger** and **Cases → trail →** tabs to see the result and the full
   protocol trace.

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
