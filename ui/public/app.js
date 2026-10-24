/* Refundry dashboard — talks to the gateway through this UI server's proxy. */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  caseId: null,
  contextId: null,
  taskId: null,
  stream: null,
};

// ---------------------------------------------------------------- helpers
async function api(path, opts = {}) {
  const res = await fetch(`/api/v1${path}`, {
    headers: { "content-type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

function toast(msg, isErr = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function money(n) {
  if (n == null) return "—";
  return "$" + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function when(ts) {
  if (ts == null || ts === "—") return "—";
  const n = Number(ts);
  const d = Number.isFinite(n) ? new Date(n > 1e12 ? n : n * 1000) : new Date(ts);
  return isNaN(d.getTime()) ? String(ts) : d.toLocaleString();
}

// ---------------------------------------------------------------- tabs
$$(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.remove("active"));
    $$(".panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $(`#tab-${t.dataset.tab}`).classList.add("active");
    if (t.dataset.tab === "cases") loadCases();
    if (t.dataset.tab === "ledger") loadLedger();
    if (t.dataset.tab === "network") loadNetwork();
  })
);

// ---------------------------------------------------------------- health
async function refreshHealth() {
  const pill = $("#health-pill");
  const text = $("#health-text");
  try {
    const h = await api("/health");
    pill.className = "pill ok";
    text.textContent = `online · ${h.reasoning} · jev:${h.jev_backend}`;
  } catch {
    pill.className = "pill bad";
    text.textContent = "gateway offline";
  }
}

async function loadConfig() {
  try {
    const cfg = await (await fetch("/_ui/config")).json();
    $("#gateway-meta").textContent = `gateway: ${cfg.gateway}`;
  } catch {}
}

// ---------------------------------------------------------------- orchestrator
async function loadOrchestrator() {
  const sel = $("#orchestrator");
  try {
    const { selected, options } = await api("/orchestrator");
    sel.innerHTML = options.map((o) => {
      const dis = o.available ? "" : " disabled";
      const suffix = o.available ? "" : " (not installed)";
      const picked = o.key === selected ? " selected" : "";
      return `<option value="${o.key}"${dis}${picked}>${escapeHtml(o.label)}${suffix}</option>`;
    }).join("");
  } catch {
    sel.innerHTML = `<option>unavailable</option>`;
  }
}

$("#orchestrator").addEventListener("change", async (e) => {
  const key = e.target.value;
  try {
    const res = await api("/orchestrator", {
      method: "PUT",
      body: JSON.stringify({ orchestrator: key }),
    });
    const label = (res.options.find((o) => o.key === res.selected) || {}).label || res.selected;
    toast(`Orchestrator set to ${label} — saved to SQLite`);
  } catch (err) {
    toast("Could not set orchestrator: " + err.message, true);
    loadOrchestrator();
  }
});

// ---------------------------------------------------------------- file claim
$("#claim-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#file-btn");
  btn.disabled = true;
  btn.textContent = "Submitting…";
  const fd = new FormData(e.target);
  const payload = {
    order_ref: fd.get("order_ref").trim(),
    buyer_ref: fd.get("buyer_ref").trim(),
    narrative: fd.get("narrative").trim(),
    evidence_refs: fd.get("evidence_refs").split("\n").map((s) => s.trim()).filter(Boolean),
  };
  try {
    const view = await api("/refunds", { method: "POST", body: JSON.stringify(payload) });
    state.caseId = view.case_id;
    state.contextId = view.context_id;
    state.taskId = view.task_id;
    renderCase(view);
    startStream(view.case_id);
    toast(`Case ${view.case_id} filed`);
  } catch (err) {
    toast("File failed: " + err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Submit claim";
  }
});

// ---------------------------------------------------------------- render case
function renderCase(view) {
  $("#case-state").textContent = view.task_state || "—";
  $("#case-state").className = "badge " + (view.task_state || "");

  const r = view.result || {};
  const amount = r.amount ?? view.approval_request?.amount;
  const engine = (view.routing && view.routing.orchestrator) || null;
  const rows = [
    ["Case", view.case_id],
    ["Status", view.status || view.task_state],
    ["Claim type", view.claim_type || "—"],
    ["Orchestrator", engine || "—"],
    ["Message", view.message || "—"],
  ];
  let html = rows.map(([k, v]) => `<div class="summary-row"><span class="k">${k}</span><span class="v">${escapeHtml(String(v))}</span></div>`).join("");
  if (amount != null) html += `<div class="summary-row"><span class="k">Amount</span><span class="v amount">${money(amount)}</span></div>`;
  $("#case-summary").innerHTML = html;

  // approval box
  if (view.awaiting_approval && view.approval_request) {
    renderApproval(view.approval_request);
  } else if (["resolved", "declined", "completed", "failed"].includes(view.task_state)) {
    $("#approval-box").classList.add("hidden");
  }
  // otherwise leave whatever is currently shown untouched

  // timeline from the task result, if any
  if (Array.isArray(view.timeline) && view.timeline.length) {
    renderTimeline(view.timeline.map((t) => ({
      who: t.agent || t.actor || "arbiter",
      act: t.action || t.state || "",
      detail: t.detail || t.note || "",
    })));
  }
}

function renderApproval(req) {
  const box = $("#approval-box");
  box.classList.remove("hidden");
  const cite = (req.citations && req.citations[0]) || null;
  const basis = cite ? `${cite.clause_id || ""} ${cite.title || ""}`.trim() : req.basis;
  const confidence = typeof req.confidence === "object"
    ? (req.confidence.why || (req.confidence.confidence != null ? String(req.confidence.confidence) : ""))
    : req.confidence;
  const rows = [
    ["Question", req.question],
    ["Amount", money(req.amount)],
    ["Tender", req.tender],
    ["Basis", basis],
    ["Risk", req.abuse || req.risk],
    ["Confidence", confidence],
  ].filter(([, v]) => v != null && v !== "");
  $("#approval-detail").innerHTML = rows
    .map(([k, v]) => `<div class="arow"><span class="k">${k}</span><span class="v">${escapeHtml(String(v))}</span></div>`)
    .join("");
}

// ---------------------------------------------------------------- SSE stream
function startStream(caseId) {
  if (state.stream) state.stream.close();
  const tl = $("#timeline");
  tl.innerHTML = "";
  const es = new EventSource(`/api/v1/refunds/${caseId}/stream`);
  state.stream = es;

  es.addEventListener("trail", (ev) => {
    try {
      const row = JSON.parse(ev.data);
      appendTimeline(row);
    } catch {}
  });
  es.addEventListener("done", async () => {
    es.close();
    // pull the final authoritative view
    try { renderCase(await fetchCaseView(caseId)); } catch {}
    toast("Case resolved");
  });
  es.addEventListener("timeout", () => es.close());
  es.onerror = () => { /* keep calm; gateway closes stream when done */ };
}

function appendTimeline(row) {
  const tl = $("#timeline");
  if (tl.querySelector(".muted")) tl.innerHTML = "";
  const who = row.actor || row.agent || row.source || "system";
  const act = row.action || row.event || row.kind || "";
  const detail = typeof row.detail === "string" ? row.detail
    : row.detail ? JSON.stringify(row.detail) : (row.target || "");
  const li = document.createElement("li");
  if (/jev/i.test(who)) li.classList.add("jev");
  li.innerHTML = `<span class="who">${escapeHtml(who)}</span><span class="act">${escapeHtml(act)}</span>` +
    (detail ? `<span class="detail">${escapeHtml(String(detail))}</span>` : "");
  tl.appendChild(li);
  tl.scrollTop = tl.scrollHeight;

  // surface an approval ask the moment it crosses the wire
  if (/input-required|approval|needs a named approver/i.test(act + " " + detail)) {
    $("#case-state").textContent = "input-required";
    $("#case-state").className = "badge input-required";
  }
}

function renderTimeline(items) {
  const tl = $("#timeline");
  tl.innerHTML = "";
  items.forEach((it) => {
    const li = document.createElement("li");
    if (/jev/i.test(it.who)) li.classList.add("jev");
    li.innerHTML = `<span class="who">${escapeHtml(it.who)}</span><span class="act">${escapeHtml(it.act)}</span>` +
      (it.detail ? `<span class="detail">${escapeHtml(String(it.detail))}</span>` : "");
    tl.appendChild(li);
  });
}

async function fetchCaseView(caseId) {
  const data = await api(`/refunds/${caseId}`);
  const rec = data.record || {};
  return {
    case_id: caseId,
    task_state: rec.status,
    status: rec.status,
    claim_type: rec.claim_type,
    message: rec.message,
    result: rec.result,
    routing: rec.routing,
    timeline: rec.timeline || [],
    awaiting_approval: rec.status === "input-required",
    approval_request: rec.approval_request,
  };
}

async function refreshCurrentCase() {
  if (!state.caseId) return;
  try { renderCase(await fetchCaseView(state.caseId)); } catch {}
}

// ---------------------------------------------------------------- approve
$("#approve-btn").addEventListener("click", () => submitApproval(true));
$("#decline-btn").addEventListener("click", () => submitApproval(false));

async function submitApproval(approved) {
  if (!state.caseId) return;
  const body = {
    approved,
    approver: $("#approver").value.trim(),
    note: $("#approve-note").value.trim(),
  };
  if (approved && !body.approver) { toast("An approval needs a named approver (MKT-060)", true); return; }
  $("#approve-btn").disabled = true;
  $("#decline-btn").disabled = true;
  try {
    const view = await api(`/refunds/${state.caseId}/approve`, { method: "POST", body: JSON.stringify(body) });
    $("#approval-box").classList.add("hidden");
    renderCase(view);
    toast(approved ? "Approved — resuming case" : "Declined");
    startStream(state.caseId);
  } catch (err) {
    toast("Approval failed: " + err.message, true);
  } finally {
    $("#approve-btn").disabled = false;
    $("#decline-btn").disabled = false;
  }
}

// ---------------------------------------------------------------- cases
async function loadCases() {
  const tb = $("#cases-table tbody");
  tb.innerHTML = `<tr><td colspan="5" class="muted">loading…</td></tr>`;
  try {
    const { cases } = await api("/cases");
    if (!cases.length) { tb.innerHTML = `<tr><td colspan="5" class="muted">no cases yet</td></tr>`; return; }
    tb.innerHTML = cases.map((c) => {
      const id = c.case_id || c.id;
      const amount = c.result?.amount ?? c.amount;
      return `<tr>
        <td>${escapeHtml(id)}</td>
        <td><span class="badge ${c.status || ""}">${escapeHtml(c.status || "—")}</span></td>
        <td>${escapeHtml(c.claim_type || "—")}</td>
        <td>${amount != null ? money(amount) : "—"}</td>
        <td><button class="ghost" data-trail="${escapeHtml(id)}">trail →</button></td>
      </tr>`;
    }).join("");
    $$("[data-trail]").forEach((b) => b.addEventListener("click", () => loadTrail(b.dataset.trail)));
  } catch (err) {
    tb.innerHTML = `<tr><td colspan="5" class="muted">${escapeHtml(err.message)}</td></tr>`;
  }
}
$("#refresh-cases").addEventListener("click", loadCases);

async function loadTrail(caseId) {
  $("#trail-card").classList.remove("hidden");
  $("#trail-case").textContent = caseId;
  const list = $("#trail-list");
  list.innerHTML = `<li class="muted">loading…</li>`;
  try {
    const { trail } = await api(`/trail/${caseId}`);
    if (!trail.length) { list.innerHTML = `<li class="muted">no trail</li>`; return; }
    list.innerHTML = trail.map((t) => {
      const who = t.actor || t.source || t.agent || "—";
      const act = t.action || t.event || t.kind || "";
      const detail = typeof t.detail === "string" ? t.detail : (t.target || "");
      return `<li><span class="tp">${escapeHtml(who)}</span><span class="ta">${escapeHtml(act)}</span> ${escapeHtml(String(detail))}</li>`;
    }).join("");
  } catch (err) {
    list.innerHTML = `<li class="muted">${escapeHtml(err.message)}</li>`;
  }
}
$("#close-trail").addEventListener("click", () => $("#trail-card").classList.add("hidden"));

// ---------------------------------------------------------------- ledger
async function loadLedger() {
  const tb = $("#ledger-table tbody");
  tb.innerHTML = `<tr><td colspan="5" class="muted">loading…</td></tr>`;
  try {
    const { ledger } = await api("/ledger");
    if (!ledger.length) { tb.innerHTML = `<tr><td colspan="5" class="muted">no refunds posted</td></tr>`; return; }
    tb.innerHTML = ledger.map((e) => `<tr>
      <td>${escapeHtml(e.refund_ref || e.ref || e.id || "—")}</td>
      <td>${escapeHtml(e.case_id || e.case || "—")}</td>
      <td>${money(e.amount)}</td>
      <td>${escapeHtml(e.tender || e.method || "—")}</td>
      <td>${escapeHtml(when(e.at || e.created_at || e.when))}</td>
    </tr>`).join("");
  } catch (err) {
    tb.innerHTML = `<tr><td colspan="5" class="muted">${escapeHtml(err.message)}</td></tr>`;
  }
}
$("#refresh-ledger").addEventListener("click", loadLedger);

// ---------------------------------------------------------------- network
async function loadNetwork() {
  loadDoctor();
  loadAgents();
  loadServers();
}
async function loadDoctor() {
  const el = $("#doctor-summary");
  el.textContent = "running doctor…";
  try {
    const d = await api("/doctor");
    const up = d.checks.filter((c) => c.ok).length;
    el.innerHTML = `<span class="${d.ok ? "st up" : "st down"}">${d.ok ? "✓ all healthy" : "✗ degraded"}</span> — ${up}/${d.checks.length} services up · jev backend: <b>${escapeHtml(d.jev_backend)}</b>`;
  } catch (err) {
    el.innerHTML = `<span class="st down">✗ ${escapeHtml(err.message)}</span>`;
  }
}
async function loadAgents() {
  const el = $("#agents-list");
  try {
    const { agents } = await api("/agents");
    el.innerHTML = agents.map((a) => `<div class="tile">
      <div><div class="name">${escapeHtml(a.name || a.key)}</div>
      <div class="sub">${a.reachable ? escapeHtml((a.skills || []).join(", ")) : "unreachable"}</div></div>
      <div class="st ${a.reachable ? "up" : "down"}">${a.reachable ? "● up" : "○ down"}</div>
    </div>`).join("");
  } catch (err) { el.innerHTML = `<p class="muted">${escapeHtml(err.message)}</p>`; }
}
async function loadServers() {
  const el = $("#servers-list");
  try {
    const { servers } = await api("/servers");
    el.innerHTML = servers.map((s) => `<div class="tile">
      <div><div class="name">${escapeHtml(s.name || s.key)}</div>
      <div class="sub">${s.reachable ? (s.stateless ? "stateless MCP" : "MCP") : "unreachable"}</div></div>
      <div class="st ${s.reachable ? "up" : "down"}">${s.reachable ? "● up" : "○ down"}</div>
    </div>`).join("");
  } catch (err) { el.innerHTML = `<p class="muted">${escapeHtml(err.message)}</p>`; }
}
$("#refresh-network").addEventListener("click", loadNetwork);

// ---------------------------------------------------------------- util
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------------------------------------------------------- boot
loadConfig();
loadOrchestrator();
refreshHealth();
setInterval(refreshHealth, 8000);
