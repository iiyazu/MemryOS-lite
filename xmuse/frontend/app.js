const API_BASE = "http://localhost:8200/api";
const REFRESH_MS = 10000;

const state = {
  lanes: [],
  errors: [],
  currentLaneId: null,
};

const pages = {
  lanes: document.getElementById("lane-overview"),
  detail: document.getElementById("lane-detail"),
  errors: document.getElementById("error-knowledge"),
  submit: document.getElementById("submit-lane"),
};

const lanesBody = document.getElementById("lanes-body");
const metricsSummary = document.getElementById("metrics-summary");
const lastUpdated = document.getElementById("last-updated");
const laneDetailTitle = document.getElementById("lane-detail-title");
const laneDetailMeta = document.getElementById("lane-detail-meta");
const lanePrompt = document.getElementById("lane-prompt");
const laneLog = document.getElementById("lane-log");
const gateResults = document.getElementById("gate-results");
const errorsCount = document.getElementById("errors-count");
const errorsList = document.getElementById("errors-list");
const errorSearch = document.getElementById("error-search");
const laneForm = document.getElementById("lane-form");
const submitStatus = document.getElementById("submit-status");

function getRoute() {
  const hash = window.location.hash.replace(/^#/, "");
  if (hash.startsWith("lane/")) {
    return { page: "detail", laneId: decodeURIComponent(hash.slice(5)) };
  }
  if (hash === "errors") {
    return { page: "errors" };
  }
  if (hash === "submit") {
    return { page: "submit" };
  }
  return { page: "lanes" };
}

function setActivePage(page) {
  for (const [name, element] of Object.entries(pages)) {
    element.classList.toggle("active", name === page);
  }

  document.querySelectorAll("nav a").forEach((link) => {
    link.classList.toggle("active", link.dataset.route === page);
  });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

function asArray(payload, keys) {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (!payload || typeof payload !== "object") {
    return [];
  }
  for (const key of keys) {
    if (Array.isArray(payload[key])) {
      return payload[key];
    }
  }
  return [];
}

function getLaneId(lane) {
  return lane.feature_id || lane.id || lane.lane_id || "";
}

function normalizeStatus(status) {
  const value = String(status || "pending").toLowerCase();
  if (["pending", "running", "done", "failed"].includes(value)) {
    return value;
  }
  return "pending";
}

function formatCapabilities(capabilities) {
  if (Array.isArray(capabilities)) {
    return capabilities.join(", ");
  }
  return capabilities || "";
}

function textOrFallback(value, fallback) {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}

function setLastUpdated(label = "Updated") {
  lastUpdated.textContent = `${label} ${new Date().toLocaleTimeString()}`;
}

function setTableMessage(message) {
  lanesBody.innerHTML = `<tr><td colspan="5" class="empty">${escapeHtml(message)}</td></tr>`;
}

function renderLanes(lanes) {
  if (!lanes.length) {
    setTableMessage("No lanes found.");
    return;
  }

  lanesBody.innerHTML = lanes
    .map((lane) => {
      const laneId = getLaneId(lane);
      const status = normalizeStatus(lane.status);
      return `
        <tr>
          <td><strong>${escapeHtml(laneId || "unknown")}</strong></td>
          <td><span class="status-badge ${status}">${status}</span></td>
          <td>${escapeHtml(lane.branch || lane.worktree || "")}</td>
          <td>${escapeHtml(formatCapabilities(lane.capabilities))}</td>
          <td><a class="detail-link" href="#lane/${encodeURIComponent(laneId)}">Open</a></td>
        </tr>
      `;
    })
    .join("");
}

function renderMetrics(metrics) {
  if (!metrics || typeof metrics !== "object") {
    metricsSummary.textContent = "";
    return;
  }

  const parts = [];
  const counts = metrics.counts || metrics.status_counts || metrics;
  for (const status of ["pending", "running", "done", "failed"]) {
    if (typeof counts[status] === "number") {
      parts.push(`${status}: ${counts[status]}`);
    }
  }
  if (typeof metrics.avg_time === "number") {
    parts.push(`avg: ${metrics.avg_time.toFixed(1)}s`);
  }
  metricsSummary.textContent = parts.join(" | ");
}

async function loadLanes() {
  try {
    const [lanePayload, metricsPayload] = await Promise.all([
      fetchJson(`${API_BASE}/lanes`),
      fetchJson(`${API_BASE}/metrics`).catch(() => null),
    ]);
    state.lanes = asArray(lanePayload, ["lanes", "items", "results"]);
    renderLanes(state.lanes);
    renderMetrics(metricsPayload);
    setLastUpdated();
  } catch (error) {
    setTableMessage(`API error: ${error.message}`);
    metricsSummary.textContent = "";
    setLastUpdated("Failed");
  }
}

function normalizeDetail(payload) {
  const lane = payload?.lane || payload || {};
  return {
    lane,
    log:
      payload?.execution_log ||
      payload?.log ||
      payload?.logs ||
      lane.execution_log ||
      lane.log ||
      "",
    gates:
      payload?.gate_results ||
      payload?.gates ||
      payload?.gate ||
      lane.gate_results ||
      lane.gates ||
      null,
  };
}

function renderGateResults(results) {
  if (!results) {
    gateResults.textContent = "No gate results available.";
    return;
  }

  if (Array.isArray(results)) {
    gateResults.innerHTML = results.map(renderGateItem).join("");
    return;
  }

  if (typeof results === "object") {
    if (typeof results.passed === "boolean" || results.errors || results.checks) {
      gateResults.innerHTML = renderGateItem(results);
      return;
    }
    gateResults.innerHTML = Object.entries(results)
      .map(([name, value]) => renderGateItem({ name, value }))
      .join("");
    return;
  }

  gateResults.innerHTML = `<pre class="pre-block">${escapeHtml(String(results))}</pre>`;
}

function renderGateItem(item) {
  const passed =
    item.passed === true ||
    item.status === "pass" ||
    item.status === "passed" ||
    item.value === true;
  const failed =
    item.passed === false ||
    item.status === "fail" ||
    item.status === "failed" ||
    item.value === false;
  const className = passed ? "pass" : failed ? "fail" : "";
  const title = item.name || item.check || item.id || "Gate";
  const body = {
    status: item.status,
    passed: item.passed,
    checks: item.checks,
    errors: item.errors,
    value: item.value,
  };
  return `
    <div class="gate-item ${className}">
      <strong>${escapeHtml(title)}</strong>
      <pre>${escapeHtml(JSON.stringify(body, null, 2))}</pre>
    </div>
  `;
}

async function loadLaneDetail(laneId) {
  if (!laneId) {
    laneDetailTitle.textContent = "Lane detail";
    laneDetailMeta.textContent = "";
    lanePrompt.textContent = "No lane selected.";
    laneLog.textContent = "No log available.";
    gateResults.textContent = "No gate results available.";
    return;
  }

  try {
    const payload = await fetchJson(`${API_BASE}/lanes/${encodeURIComponent(laneId)}`);
    const detail = normalizeDetail(payload);
    const lane = detail.lane;
    const status = normalizeStatus(lane.status);

    laneDetailTitle.textContent = getLaneId(lane) || laneId;
    laneDetailMeta.innerHTML = `<span class="status-badge ${status}">${status}</span>`;
    lanePrompt.textContent = textOrFallback(lane.prompt, "No prompt available.");
    laneLog.textContent = textOrFallback(detail.log, "No log available.");
    renderGateResults(detail.gates);
    setLastUpdated();
  } catch (error) {
    laneDetailTitle.textContent = laneId;
    laneDetailMeta.textContent = `API error: ${error.message}`;
    lanePrompt.textContent = "No prompt available.";
    laneLog.textContent = "No log available.";
    gateResults.textContent = "No gate results available.";
    setLastUpdated("Failed");
  }
}

function normalizeError(error) {
  return {
    id: error.record_id || error.id || error.error_id || "error",
    title: error.summary || error.pattern || error.fingerprint || error.pit || "Error pattern",
    feature: error.feature_id || error.lane_id || "",
    rootCause: error.root_cause || error.root_cause_status || "",
    trigger: error.trigger || "",
    fix: error.fix || "",
    verification: error.verification || error.verification_evidence || "",
    lesson: error.lesson || "",
    scope: error.scope || "",
    raw: error,
  };
}

function renderErrors() {
  const query = errorSearch.value.trim().toLowerCase();
  const normalized = state.errors.map(normalizeError);
  const filtered = query
    ? normalized.filter((error) => JSON.stringify(error.raw).toLowerCase().includes(query))
    : normalized;

  errorsCount.textContent = `${filtered.length} of ${normalized.length} patterns`;

  if (!filtered.length) {
    errorsList.innerHTML = '<p class="empty">No matching errors.</p>';
    return;
  }

  errorsList.innerHTML = filtered
    .map(
      (error) => `
        <article class="error-card">
          <h3>${escapeHtml(error.title)}</h3>
          <p class="muted">${escapeHtml(error.id)}${error.feature ? ` | ${escapeHtml(error.feature)}` : ""}</p>
          <dl>
            ${renderDefinition("Root cause", error.rootCause)}
            ${renderDefinition("Trigger", error.trigger)}
            ${renderDefinition("Fix", error.fix)}
            ${renderDefinition("Verification", error.verification)}
            ${renderDefinition("Lesson", error.lesson)}
            ${renderDefinition("Scope", error.scope)}
          </dl>
        </article>
      `,
    )
    .join("");
}

function renderDefinition(label, value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  return `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(textOrFallback(value, ""))}</dd>`;
}

async function loadErrors() {
  try {
    const payload = await fetchJson(`${API_BASE}/errors`);
    state.errors = asArray(payload, ["errors", "entries", "items", "results"]);
    renderErrors();
    setLastUpdated();
  } catch (error) {
    errorsList.innerHTML = `<p class="empty">API error: ${escapeHtml(error.message)}</p>`;
    errorsCount.textContent = "";
    setLastUpdated("Failed");
  }
}

async function submitLane(event) {
  event.preventDefault();
  submitStatus.textContent = "Submitting...";

  const formData = new FormData(laneForm);
  const capabilities = String(formData.get("capabilities") || "")
    .split(",")
    .map((capability) => capability.trim())
    .filter(Boolean);

  const payload = {
    feature_id: String(formData.get("feature_id") || "").trim(),
    prompt: String(formData.get("prompt") || "").trim(),
    capabilities,
  };

  try {
    await fetchJson(`${API_BASE}/lanes`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    laneForm.reset();
    submitStatus.textContent = `Submitted ${payload.feature_id}.`;
    window.location.hash = "#lanes";
    await loadLanes();
  } catch (error) {
    submitStatus.textContent = `Submit failed: ${error.message}`;
  }
}

async function refreshCurrentView() {
  const route = getRoute();
  setActivePage(route.page);
  state.currentLaneId = route.laneId || null;

  if (route.page === "detail") {
    await loadLaneDetail(route.laneId);
    return;
  }
  if (route.page === "errors") {
    await loadErrors();
    return;
  }
  if (route.page === "submit") {
    setLastUpdated();
    return;
  }
  await loadLanes();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });
}

document.getElementById("refresh-lanes").addEventListener("click", loadLanes);
document.getElementById("refresh-detail").addEventListener("click", () => {
  loadLaneDetail(state.currentLaneId);
});
errorSearch.addEventListener("input", renderErrors);
laneForm.addEventListener("submit", submitLane);
window.addEventListener("hashchange", refreshCurrentView);

if (!window.location.hash) {
  window.location.hash = "#lanes";
}

refreshCurrentView();
setInterval(refreshCurrentView, REFRESH_MS);
