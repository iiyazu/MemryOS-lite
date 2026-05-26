const API_BASE = "http://localhost:8200/api";
const REFRESH_MS = 5000;

const state = { lanes: [], selected: null, errors: [] };

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const laneList = $("#lane-list");
const messages = $("#messages");
const chatHeader = $("#chat-header");
const inputBar = $("#input-bar");
const stats = $("#stats");
const search = $("#search");
const modal = $("#new-lane-modal");

function statusIcon(s) {
  return { done: "✓", failed: "✗", running: "◉", pending: "○" }[s] || "○";
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}

function normStatus(s) {
  const v = String(s || "pending").toLowerCase();
  return ["pending", "running", "done", "failed"].includes(v) ? v : "pending";
}

function renderLaneList() {
  const q = search.value.toLowerCase();
  const filtered = state.lanes.filter(
    (l) => !q || (l.feature_id || "").toLowerCase().includes(q)
  );
  laneList.innerHTML = filtered
    .map((l) => {
      const s = normStatus(l.status);
      const active = state.selected === l.feature_id ? "active" : "";
      const preview = (l.prompt || "").slice(0, 60);
      return `<li class="lane-item ${active}" data-id="${esc(l.feature_id)}">
        <div class="lane-avatar ${s}">${statusIcon(s)}</div>
        <div class="lane-info">
          <div class="lane-name">${esc(l.feature_id)}</div>
          <div class="lane-preview">${esc(preview)}</div>
        </div>
        <span class="lane-badge ${s}">${s}</span>
      </li>`;
    })
    .join("");
}

function renderStats() {
  const counts = { done: 0, failed: 0, running: 0, pending: 0 };
  state.lanes.forEach((l) => { counts[normStatus(l.status)]++; });
  stats.innerHTML = `<span style="color:#4caf50">${counts.done} done</span> · `
    + `<span style="color:#ef5350">${counts.failed} failed</span> · `
    + `<span style="color:#4fc3f7">${counts.running} running</span> · `
    + `<span style="color:#fbbf24">${counts.pending} pending</span>`;
}

async function selectLane(id) {
  state.selected = id;
  renderLaneList();
  inputBar.style.display = "flex";
  const title = chatHeader.querySelector(".chat-title");
  const meta = chatHeader.querySelector(".chat-meta");
  title.textContent = id;
  messages.innerHTML = '<div class="empty-state">Loading...</div>';

  try {
    const detail = await fetch(`${API_BASE}/lanes/${encodeURIComponent(id)}`).then(r => r.json());
    const lane = detail.lane || detail;
    const s = normStatus(lane.status);
    meta.innerHTML = `<span class="lane-badge ${s}">${s}</span> · ${esc(lane.branch || "")}`;
    renderMessages(lane, detail);
  } catch (e) {
    messages.innerHTML = `<div class="msg error"><div class="msg-label">Error</div>${esc(e.message)}</div>`;
  }
}

function renderMessages(lane, detail) {
  let html = "";

  // Prompt as user message
  if (lane.prompt) {
    html += `<div class="msg user"><div class="msg-label">Prompt</div>${esc(lane.prompt)}</div>`;
  }

  // Dependencies
  const deps = lane.depends_on || [];
  if (deps.length) {
    html += `<div class="msg system"><div class="msg-label">Dependencies</div>${deps.map(d => esc(d)).join(", ")}</div>`;
  }

  // Execution log
  const log = detail.execution_log || detail.log || lane.execution_log || lane.log || "";
  if (log) {
    html += `<div class="msg system"><div class="msg-label">Execution Log</div><pre>${esc(log)}</pre></div>`;
  }

  // Gate results
  const gates = detail.gate_results || detail.gates || lane.gate_results || null;
  if (gates) {
    const gateClass = gates.passed ? "success" : "error";
    html += `<div class="msg ${gateClass}"><div class="msg-label">Quality Gate</div><pre>${esc(JSON.stringify(gates, null, 2))}</pre></div>`;
  }

  // Status message
  const s = normStatus(lane.status);
  if (s === "done") {
    html += `<div class="msg success"><div class="msg-label">Complete</div>Lane finished successfully.</div>`;
  } else if (s === "failed") {
    html += `<div class="msg error"><div class="msg-label">Failed</div>Lane execution failed.</div>`;
  } else if (s === "running") {
    html += `<div class="msg system"><div class="msg-label">Status</div>Currently executing...</div>`;
  }

  messages.innerHTML = html || '<div class="empty-state">No execution data yet</div>';
  messages.scrollTop = messages.scrollHeight;
}

async function loadLanes() {
  try {
    const payload = await fetch(`${API_BASE}/lanes`).then(r => r.json());
    state.lanes = Array.isArray(payload) ? payload : (payload.lanes || payload.items || []);
    renderLaneList();
    renderStats();
    if (state.selected) selectLane(state.selected);
  } catch (e) {
    stats.textContent = "API offline";
  }
}

// Event handlers
laneList.addEventListener("click", (e) => {
  const item = e.target.closest(".lane-item");
  if (item) selectLane(item.dataset.id);
});

search.addEventListener("input", renderLaneList);

$("#new-lane-btn").addEventListener("click", () => { modal.style.display = "flex"; });
$("#modal-close").addEventListener("click", () => { modal.style.display = "none"; });

$("#lane-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    feature_id: fd.get("feature_id").trim(),
    prompt: fd.get("prompt").trim(),
    capabilities: fd.get("capabilities").split(",").map(s => s.trim()).filter(Boolean),
  };
  try {
    await fetch(`${API_BASE}/lanes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    modal.style.display = "none";
    e.target.reset();
    await loadLanes();
  } catch (err) {
    alert("Failed: " + err.message);
  }
});

$("#send-btn").addEventListener("click", () => {
  const input = $("#msg-input");
  const text = input.value.trim();
  if (!text || !state.selected) return;
  messages.innerHTML += `<div class="msg user"><div class="msg-label">You</div>${esc(text)}</div>`;
  messages.scrollTop = messages.scrollHeight;
  input.value = "";
});

// Init
loadLanes();
setInterval(loadLanes, REFRESH_MS);
