/**
 * Refundry UI — Node.js server.
 *
 *   Browser ──▶ this Express server ──▶ Refundry gateway (FastAPI, :8080)
 *
 * It does two things and nothing else:
 *   1. Serves the static single-page dashboard in ./public
 *   2. Proxies every /api/* and /health request through to the Python
 *      gateway, including the Server-Sent-Events stream used for the live
 *      case timeline.
 *
 * Keeping the UI behind this proxy means the browser only ever talks to one
 * origin, so there is no CORS to reason about and the gateway URL is
 * configured in exactly one place (the GATEWAY_URL env var).
 */

import path from "node:path";
import { fileURLToPath } from "node:url";
import express from "express";
import { createProxyMiddleware } from "http-proxy-middleware";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PORT = Number(process.env.PORT || process.env.UI_PORT || 3000);
const GATEWAY_URL =
  process.env.GATEWAY_URL || process.env.REFUNDRY_GATEWAY || "http://127.0.0.1:8080";

const app = express();

// --- proxy API + health straight through to the Refundry gateway ----------
const proxy = createProxyMiddleware({
  target: GATEWAY_URL,
  changeOrigin: true,
  ws: false,
  // SSE needs the response flushed as it arrives, not buffered.
  selfHandleResponse: false,
  onError(err, _req, res) {
    if (res.headersSent) return;
    res.status(502).json({
      error: "gateway_unreachable",
      detail: `Could not reach the Refundry gateway at ${GATEWAY_URL}. Is 'make run' up?`,
      cause: err.message,
    });
  },
});

app.use("/api", proxy);
app.use("/health", proxy);

// --- static dashboard ------------------------------------------------------
app.use(express.static(path.join(__dirname, "public")));

// Tiny endpoint so the frontend can display which gateway it is pointed at.
app.get("/_ui/config", (_req, res) => {
  res.json({ gateway: GATEWAY_URL });
});

app.listen(PORT, () => {
  console.log("");
  console.log("  Refundry UI");
  console.log(`  ▶ open      http://127.0.0.1:${PORT}`);
  console.log(`  ▶ gateway   ${GATEWAY_URL}`);
  console.log("");
});
