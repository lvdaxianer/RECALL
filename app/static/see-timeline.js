const state = {
  requestId: "",
  query: "",
  retrievedIds: [],
};

const eventCards = new Map(
  Array.from(document.querySelectorAll("[data-event]")).map((card) => [card.dataset.event, card])
);

document.getElementById("search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  resetTimeline();
  await runOptimizeStream();
});

document.getElementById("invalidate-cache").addEventListener("click", async () => {
  if (!state.requestId) {
    return;
  }
  const response = await fetch(`/api/v1/rag/cache/rerank/invalidate-by-request/${state.requestId}`, {
    method: "POST",
  });
  appendLog("cache.invalidate", await response.json());
});

document.getElementById("feedback-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.requestId) {
    return;
  }
  const userId = document.getElementById("user-id").value.trim();
  const response = await fetch(`/api/v1/rag/${encodeURIComponent(userId)}/feedback/bad-case`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      query: state.query,
      retrieved_ids: state.retrievedIds,
      miss_reason: document.getElementById("miss-reason").value,
      human_label: "bad",
      request_id: state.requestId,
    }),
  });
  appendLog("feedback.bad_case", await response.json());
});

document.getElementById("load-history").addEventListener("click", async () => {
  await loadSessions();
});

document.getElementById("session-select").addEventListener("change", async () => {
  await loadRuns();
});

document.getElementById("replay-run").addEventListener("click", async () => {
  await replaySelectedRun();
});

async function runOptimizeStream() {
  const userId = document.getElementById("user-id").value.trim();
  state.query = document.getElementById("query-input").value.trim();
  const response = await fetch(`/api/v1/rag/${encodeURIComponent(userId)}/search/optimize/stream`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      input: state.query,
      type: document.getElementById("search-type").value,
      topK: Number(document.getElementById("top-k").value || 20),
      threshold: 0,
      enableFeatureBoost: document.getElementById("feature-boost").checked,
    }),
  });
  await readSseStream(response);
}

async function loadSessions() {
  const userId = document.getElementById("user-id").value.trim();
  const response = await fetch(`/api/v1/agent/${encodeURIComponent(userId)}/sessions`);
  const body = await response.json();
  const select = document.getElementById("session-select");
  select.innerHTML = (body.data || [])
    .map((session) => `<option value="${escapeHtml(session.session_id)}">${escapeHtml(session.title || session.session_id)}</option>`)
    .join("");
  await loadRuns();
}

async function loadRuns() {
  const userId = document.getElementById("user-id").value.trim();
  const sessionId = document.getElementById("session-select").value;
  const select = document.getElementById("run-select");
  if (!sessionId) {
    select.innerHTML = "";
    return;
  }
  const response = await fetch(`/api/v1/agent/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(sessionId)}/runs`);
  const body = await response.json();
  select.innerHTML = (body.data || [])
    .map((run) => `<option value="${escapeHtml(run.run_id)}">${escapeHtml(run.input || run.run_id)}</option>`)
    .join("");
}

async function replaySelectedRun() {
  const userId = document.getElementById("user-id").value.trim();
  const sessionId = document.getElementById("session-select").value;
  const runId = document.getElementById("run-select").value;
  if (!sessionId || !runId) {
    return;
  }
  resetTimeline();
  const response = await fetch(
    `/api/v1/agent/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(sessionId)}/events?run_id=${encodeURIComponent(runId)}`
  );
  const body = await response.json();
  (body.data || []).forEach((eventData) => {
    renderTimelineEvent(eventData.event, eventData);
    appendLog(eventData.event, eventData);
  });
}

async function readSseStream(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const {done, value} = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, {stream: true});
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    blocks.filter(Boolean).forEach(handleSseBlock);
  }
  if (buffer.trim()) {
    handleSseBlock(buffer);
  }
}

function handleSseBlock(block) {
  const lines = block.split("\n");
  const eventName = (lines.find((line) => line.startsWith("event:")) || "event: message")
    .replace("event:", "")
    .trim();
  const dataLine = lines.find((line) => line.startsWith("data:"));
  const eventData = dataLine ? JSON.parse(dataLine.replace("data:", "").trim()) : {};
  renderTimelineEvent(eventName, eventData);
  appendLog(eventName, eventData);
}

function renderTimelineEvent(eventName, eventData) {
  rememberRequest(eventData);
  rememberRetrievedIds(eventName, eventData);
  const card = eventCards.get(eventName);
  if (!card) {
    return;
  }
  card.classList.add("is-filled");
  card.innerHTML = buildCardHtml(eventName, eventData.payload || {});
}

function rememberRequest(eventData) {
  if (!eventData.request_id) {
    return;
  }
  state.requestId = eventData.request_id;
  document.getElementById("request-id").textContent = `request_id: ${state.requestId}`;
  document.getElementById("invalidate-cache").disabled = false;
  document.getElementById("bad-feedback").disabled = false;
}

function rememberRetrievedIds(eventName, eventData) {
  if (eventName !== "retrieval.optimized.completed") {
    return;
  }
  state.retrievedIds = eventData.payload?.result_ids || [];
}

function buildCardHtml(eventName, payload) {
  if (eventName === "query.decomposition") {
    return `
      <h3>${escapeHtml(eventName)}</h3>
      <p>${escapeHtml(payload.intent || "-")}</p>
      ${renderList("cot_plan", payload.cot_plan || [])}
      ${renderList("expanded_queries", payload.expanded_queries || [])}
    `;
  }
  if (eventName === "rerank.completed") {
    return `
      <h3>${escapeHtml(eventName)}</h3>
      <dl>
        <dt>candidate_count</dt><dd>${payload.candidate_count ?? 0}</dd>
        <dt>skipped</dt><dd>${String(Boolean(payload.skipped))}</dd>
        <dt>reason</dt><dd>${escapeHtml(payload.reason || "-")}</dd>
      </dl>
      <pre>${escapeHtml(JSON.stringify(payload.timings_ms || {}, null, 2))}</pre>
    `;
  }
  if (eventName === "recommendation.completed") {
    return `
      <h3>${escapeHtml(eventName)}</h3>
      <p>recommendation_count: ${payload.recommendation_count ?? 0}</p>
      ${renderList("recommended_ids", payload.recommended_ids || [])}
    `;
  }
  return `
    <h3>${escapeHtml(eventName)}</h3>
    <pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
  `;
}

function renderList(title, items) {
  return `
    <section>
      <h4>${escapeHtml(title)}</h4>
      <ul>${items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>
    </section>
  `;
}

function appendLog(eventName, eventData) {
  const log = document.getElementById("event-log");
  log.textContent += `${eventName}\n${JSON.stringify(eventData, null, 2)}\n\n`;
}

function resetTimeline() {
  state.requestId = "";
  state.retrievedIds = [];
  document.getElementById("request-id").textContent = "request_id: -";
  document.getElementById("event-log").textContent = "";
  document.getElementById("invalidate-cache").disabled = true;
  document.getElementById("bad-feedback").disabled = true;
  eventCards.forEach((card, eventName) => {
    card.classList.remove("is-filled");
    card.innerHTML = `<h3>${eventName}</h3><p>-</p>`;
  });
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

resetTimeline();
