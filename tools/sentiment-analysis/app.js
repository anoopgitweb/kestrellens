const mode = document.body.dataset.mode || "sentiment";
const state = {
  file: null,
  dataUrl: "",
  columns: [],
  last: null,
  rows: [],
  filteredRows: [],
  selectedRowIndex: 0,
  cloudMode: "single",
  filters: { sentiment: "", search: "" },
  loadingTimer: null,
  loadingClockTimer: null,
  progressPollTimer: null,
  loadingStartedAt: 0,
  loadingPercent: 0,
  loadingMessageIndex: 0,
  loadingProcessedRows: 0,
  loadingDisplayedRows: 0,
  loadingProgressMessage: "Preparing file...",
  analysisId: "",
  totalRows: 0,
  run: null,
};
const $ = (id) => document.getElementById(id);

const progressMessages = [
  "Reading uploaded feedback...",
  "Mapping verbatim field...",
  "Running sentiment engine...",
  "Calculating confidence scores...",
  "Building dashboard cards...",
  "Preparing word cloud insights...",
];

function switchTab(tabName) {
  document.querySelectorAll("[data-tab]").forEach((section) => section.classList.toggle("hidden", section.dataset.tab !== tabName));
  document.querySelectorAll("[data-tab-target]").forEach((button) => button.classList.toggle("active", button.dataset.tabTarget === tabName));
}

function setOptions(select, columns, selected = "") {
  if (!select) return;
  select.innerHTML = `<option value="">-- None --</option>` + columns.map((col) => `<option value="${escapeHtml(col)}" ${col === selected ? "selected" : ""}>${escapeHtml(col)}</option>`).join("");
}

async function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function inspectFile(file) {
  state.file = file;
  state.dataUrl = await fileToDataUrl(file);
  $("fileStatus").textContent = `Reading ${file.name}...`;
  const response = await fetch("/api/sentiment/inspect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, name: file.name, data: state.dataUrl }),
  });
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error || "Could not inspect file.");
  state.columns = payload.columns || [];
  state.totalRows = Number(payload.rows || 0);
  $("fileStatus").textContent = `${file.name} loaded. ${payload.rows.toLocaleString()} rows and ${state.columns.length} columns detected.`;
  setOptions($("feedbackCol"), state.columns, payload.guesses?.feedback || "");
  setOptions($("agentCol"), state.columns, payload.guesses?.agent || "");
  setOptions($("managerCol"), state.columns, payload.guesses?.manager || "");
  setOptions($("dateCol"), state.columns, payload.guesses?.date || "");
  setOptions($("scoreCol"), state.columns, "");
  setOptions($("dimensionSelect"), state.columns, "");
  $("analyzeBtn").disabled = false;
  switchTab("setup");
}

function friendlyError(message) {
  if (String(message || "").toLowerCase().includes("unknown endpoint")) {
    return "New analysis endpoint is not active yet. Restart the local 8765 server, then upload again.";
  }
  return message || "Something went wrong while reading the file.";
}

async function loadDefaults() {
  try {
    const response = await fetch("/api/sentiment/status");
    const payload = await response.json();
    $("sparrowModelPath").value = payload.model_status?.sparrow?.path || "";
    $("vultureModelPath").value = payload.model_status?.vulture?.path || "";
  } catch (_) {}
}

function startLoading() {
  state.loadingStartedAt = Date.now();
  state.loadingPercent = 0;
  state.loadingProcessedRows = 0;
  state.loadingDisplayedRows = 0;
  state.loadingProgressMessage = "Preparing sentiment analysis...";
  state.analysisId = `sentiment-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const engine = $("sentimentEngine").value;
  $("loadingOverlay").classList.remove("hidden");
  $("loadingOverlay").classList.remove("complete");
  $("loadingMessage").textContent = `${state.loadingProgressMessage} (${engineLabel(engine)} mode)`;
  updateLoadingMeta(0);
  $("progressBar").style.width = "0%";
  clearInterval(state.loadingTimer);
  clearInterval(state.loadingClockTimer);
  clearInterval(state.progressPollTimer);

  state.loadingClockTimer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - state.loadingStartedAt) / 1000);
    updateLoadingMeta(elapsed);
  }, 1000);

  state.loadingTimer = setInterval(advanceDisplayedRows, 16);
  state.progressPollTimer = setInterval(pollModuleProgress, 1000);
  pollModuleProgress();
  return state.analysisId;
}

function updateLoadingMeta(elapsed) {
  const total = Math.max(0, Number(state.totalRows || state.rows.length || 0));
  const processed = total ? Math.min(state.loadingDisplayedRows, total) : 0;
  const percent = total ? Math.round((processed / total) * 100) : state.loadingPercent;
  $("loadingRowNumber").textContent = processed.toLocaleString();
  $("loadingTotalRows").textContent = total.toLocaleString();
  $("loadingElapsed").textContent = `${elapsed}s`;
  $("loadingPercent").textContent = `${percent}%`;
  $("loadingMeta").textContent = `Currently reviewing row ${processed.toLocaleString()} of ${total.toLocaleString()} - ${percent}% complete`;
  $("progressBar").style.width = `${Math.max(state.loadingPercent, percent)}%`;
}

function advanceDisplayedRows() {
  const total = Math.max(0, Number(state.totalRows || state.rows.length || 0));
  const target = total ? Math.min(Number(state.loadingProcessedRows || 0), total) : 0;
  if (state.loadingDisplayedRows < target) {
    state.loadingDisplayedRows += 1;
    updateLoadingMeta(Math.floor((Date.now() - state.loadingStartedAt) / 1000));
  }
}

async function pollModuleProgress() {
  if (!state.analysisId) return;
  try {
    const response = await fetch(`/api/sentiment/progress?id=${encodeURIComponent(state.analysisId)}`, { cache: "no-store" });
    const progress = await response.json();
    if (!progress.ok) return;
    const engine = $("sentimentEngine").value;
    state.loadingPercent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
    state.loadingProcessedRows = Math.max(0, Number(progress.done || progress.currentRow || 0));
    if (Number(progress.total || 0)) state.totalRows = Number(progress.total);
    state.loadingProgressMessage = progress.message || state.loadingProgressMessage;
    $("loadingMessage").textContent = `${state.loadingProgressMessage} (${engineLabel(engine)} mode)`;
    updateLoadingMeta(Math.floor((Date.now() - state.loadingStartedAt) / 1000));
  } catch (_) {}
}

function stopLoading(showSuccess = false) {
  clearInterval(state.loadingClockTimer);
  clearInterval(state.progressPollTimer);
  state.loadingClockTimer = null;
  state.progressPollTimer = null;
  const elapsed = Math.floor((Date.now() - state.loadingStartedAt) / 1000);
  const total = Math.max(0, Number(state.totalRows || state.rows.length || 0));
  state.loadingProcessedRows = total;
  if (!showSuccess) {
    clearInterval(state.loadingTimer);
    state.loadingTimer = null;
    $("loadingOverlay").classList.add("hidden");
    return;
  }
  const finish = () => {
    clearInterval(state.loadingTimer);
    state.loadingTimer = null;
    state.loadingDisplayedRows = total;
    state.loadingPercent = 100;
    $("loadingOverlay").classList.add("complete");
    $("loadingMessage").textContent = "Finalizing dashboard and insight cards...";
    updateLoadingMeta(elapsed);
    setTimeout(() => {
      $("loadingOverlay").classList.add("hidden");
      if (showSuccess) showSuccessToast(total, elapsed);
    }, 450);
  };
  if (state.loadingDisplayedRows >= total || !total) {
    finish();
    return;
  }
  const drainTimer = setInterval(() => {
    if (state.loadingDisplayedRows >= total) {
      clearInterval(drainTimer);
      finish();
    }
  }, 25);
}

function engineLabel(value) {
  return ({ local: "Local", sparrow: "Sparrow", openai: "OpenAI API", claude: "Claude API" }[value] || value || "Selected");
}

async function analyze() {
  if (!state.file) return;
  if (!$("feedbackCol").value) {
    alert("Map the verbatim / feedback field before analysis.");
    return;
  }
  $("analyzeBtn").disabled = true;
  $("analyzeBtn").textContent = "Analyzing...";
  const analysisId = startLoading();
  let completed = false;
  state.run = {
    id: analysisId,
    fileName: state.file.name,
    startedAt: new Date(),
    endedAt: null,
    durationMs: 0,
    mode: engineLabel($("sentimentEngine").value),
    rows: state.totalRows,
    feedbackColumn: $("feedbackCol").value,
    agentColumn: $("agentCol").value || "Not mapped",
    managerColumn: $("managerCol").value || "Not mapped",
    dateColumn: $("dateCol").value || "Not mapped",
    status: "Running",
  };
  try {
    const body = {
      analysisId,
      mode,
      name: state.file.name,
      data: state.dataUrl,
      mapping: {
        feedback: $("feedbackCol").value,
        score: "",
        agent: $("agentCol").value,
        manager: $("managerCol").value,
        date: $("dateCol").value,
      },
      engines: { sentiment: $("sentimentEngine").value, theme: "local" },
      modelPaths: { sparrow: $("sparrowModelPath").value, vulture: "", apiKey: $("apiKey")?.value || "" },
      dimensions: [],
      customCategories: [],
    };
    const response = await fetch("/api/sentiment/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!payload.ok) throw new Error(payload.error || "Analysis failed.");
    state.run.endedAt = new Date();
    state.run.durationMs = state.run.endedAt - state.run.startedAt;
    state.run.rows = payload.summary?.total || state.totalRows;
    state.run.status = "Completed";
    state.last = payload;
    state.rows = normalizeRows(payload.rows || []);
    applyFilters();
    renderResults(payload);
    renderWordCloud();
    switchTab("dashboard");
    completed = true;
  } finally {
    stopLoading(completed);
    $("analyzeBtn").disabled = false;
    $("analyzeBtn").textContent = "Perform Sentiment Analysis";
  }
}

function showSuccessToast(total, elapsed) {
  const toast = $("successToast");
  if (!toast) return;
  $("successToastMeta").textContent = `${Number(total || 0).toLocaleString()} rows analyzed in ${elapsed}s. Dashboard is ready.`;
  toast.classList.remove("hidden");
  clearTimeout(state.successToastTimer);
  state.successToastTimer = setTimeout(() => toast.classList.add("hidden"), 5200);
}

function normalizeRows(rows) {
  const sentimentMode = engineLabel($("sentimentEngine").value);
  return rows.map((row, index) => ({
    ...row,
    __row_id: row.__row_id ?? String(index),
    "Confidence %": confidenceFromScore(row["Sentiment Score"]),
    "Sentiment Mode": sentimentMode,
    "Review Status": row["Review Status"] || "",
  }));
}

function confidenceFromScore(score) {
  const value = Math.abs(Number(score || 0));
  return Math.round(Math.max(52, Math.min(99, value * 100)));
}

function applyFilters() {
  const search = state.filters.search.trim().toLowerCase();
  state.filteredRows = state.rows.filter((row) => {
    const sentimentMatch = !state.filters.sentiment || row.Sentiment === state.filters.sentiment;
    const searchFields = ["Verbatim Feedback", "Agent Name", "Manager/TL", "Feedback Date", "Analysis Source", "Review Status"];
    const searchMatch = !search || searchFields.some((field) => String(row[field] || "").toLowerCase().includes(search));
    return sentimentMatch && searchMatch;
  });
}

function renderResults(payload) {
  if (!payload) return;
  const rows = state.filteredRows;
  $("results").classList.remove("hidden");
  renderRunDetails();
  const counts = sentimentCounts(rows);
  const total = rows.length;
  const cards = [
    ["Responses", total, "Rows in current view", detailForMetric("Responses", total, rows)],
    ["Positive", percent(counts.Positive, total), `${counts.Positive} entries`, detailForMetric("Positive", counts.Positive, rows)],
    ["Neutral", percent(counts.Neutral, total), `${counts.Neutral} entries`, detailForMetric("Neutral", counts.Neutral, rows)],
    ["Negative", percent(counts.Negative, total), `${counts.Negative} entries`, detailForMetric("Negative", counts.Negative, rows)],
    ["Avg Confidence", `${averageConfidence(rows)}%`, "Mean confidence score", detailForMetric("Avg Confidence", averageConfidence(rows), rows)],
  ];
  $("metricGrid").innerHTML = cards.map(([label, value, note, detail], index) => metricCardHtml(label, value, note, detail, rows, index)).join("");
  $("metricGrid").querySelectorAll("[data-card-detail]").forEach((card) => {
    card.addEventListener("dblclick", () => showDetail(card.dataset.cardTitle || "Metric", card.querySelector("template").innerHTML));
  });
  const sentimentRows = [
    { Label: "Positive", Value: counts.Positive },
    { Label: "Neutral", Value: counts.Neutral },
    { Label: "Negative", Value: counts.Negative },
  ];
  renderBar("sentimentChart", sentimentRows, "#009b9b", { noteId: "sentimentChartNote", note: sentimentInsight(counts, total), palette: ["#00a7a7", "#7893aa", "#d94045"] });
  renderBar("confidenceChart", confidenceBuckets(rows), "#d69222", { noteId: "confidenceChartNote", note: confidenceInsight(rows) });
  renderOwnerSentimentChart(rows);
  renderSentimentTrendChart(rows);
  renderInsights(payload.intelligenceCards || payload.insights || []);
  renderRowsTable();
}

function metricCardHtml(label, value, note, detail, rows, index) {
  const config = metricConfig(label, rows);
  const donut = config.showDonut ? donutSvg(config.percentValue, config.color) : "";
  return `
    <div class="metric-card metric-${config.key}" data-card-detail="${index}" data-card-title="${escapeHtml(label)}" title="Double click for calculation details">
      <div class="metric-card-main">
        <div class="metric-icon" aria-hidden="true">${config.icon}</div>
        <div>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          <small>${escapeHtml(note)}</small>
        </div>
      </div>
      ${donut}
      <template>${escapeHtml(detail)}</template>
    </div>
  `;
}

function metricConfig(label, rows) {
  const counts = sentimentCounts(rows);
  const total = Math.max(rows.length, 1);
  const configs = {
    Responses: { key: "responses", icon: "Rows", color: "#00a7a7", showDonut: false, percentValue: 100 },
    Positive: { key: "positive", icon: "+", color: "#00a86b", showDonut: true, percentValue: (counts.Positive / total) * 100 },
    Neutral: { key: "neutral", icon: "=", color: "#7893aa", showDonut: true, percentValue: (counts.Neutral / total) * 100 },
    Negative: { key: "negative", icon: "!", color: "#d94045", showDonut: true, percentValue: (counts.Negative / total) * 100 },
    "Avg Confidence": { key: "confidence", icon: "%", color: "#d69222", showDonut: true, percentValue: averageConfidence(rows) },
  };
  return configs[label] || { key: "default", icon: "AI", color: "#00a7a7", showDonut: false, percentValue: 0 };
}

function donutSvg(value, color) {
  const percentValue = Math.max(0, Math.min(100, Number(value || 0)));
  const radius = 18;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percentValue / 100) * circumference;
  return `
    <svg class="metric-donut" viewBox="0 0 46 46" role="img" aria-label="${percentValue.toFixed(1)} percent">
      <circle cx="23" cy="23" r="${radius}" fill="none" stroke="#eaf1f6" stroke-width="6"></circle>
      <circle cx="23" cy="23" r="${radius}" fill="none" stroke="${color}" stroke-width="6" stroke-linecap="round" stroke-dasharray="${circumference.toFixed(2)}" stroke-dashoffset="${offset.toFixed(2)}" transform="rotate(-90 23 23)"></circle>
      <text x="23" y="26" text-anchor="middle">${Math.round(percentValue)}</text>
    </svg>
  `;
}

function sentimentCounts(rows) {
  return rows.reduce((acc, row) => {
    acc[row.Sentiment] = (acc[row.Sentiment] || 0) + 1;
    return acc;
  }, { Positive: 0, Neutral: 0, Negative: 0 });
}

function renderRunDetails() {
  const target = $("runDetails");
  if (!target || !state.run) return;
  const run = state.run;
  target.classList.remove("hidden");
  const items = [
    ["Started", formatDateTime(run.startedAt)],
    ["Ended", run.endedAt ? formatDateTime(run.endedAt) : "In progress"],
    ["Duration", formatDuration(run.durationMs || (Date.now() - run.startedAt.getTime()))],
    ["Mode", run.mode],
    ["Rows", Number(run.rows || 0).toLocaleString()],
    ["File", run.fileName],
    ["Verbatim Field", run.feedbackColumn],
    ["Status", run.status],
  ];
  target.innerHTML = `
    <div class="run-title">
      <span>Run Details</span>
      <strong>${escapeHtml(run.mode)} analysis</strong>
    </div>
    <div class="run-grid">${items.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</div>
  `;
}

function percent(value, total) {
  return total ? `${((Number(value || 0) / total) * 100).toFixed(1)}%` : "0.0%";
}

function averageConfidence(rows) {
  if (!rows.length) return 0;
  return Math.round(rows.reduce((sum, row) => sum + Number(row["Confidence %"] || 0), 0) / rows.length);
}

function confidenceBuckets(rows) {
  const buckets = { "50-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90+": 0 };
  rows.forEach((row) => {
    const confidence = Number(row["Confidence %"] || 0);
    if (confidence >= 90) buckets["90+"] += 1;
    else if (confidence >= 80) buckets["80-89"] += 1;
    else if (confidence >= 70) buckets["70-79"] += 1;
    else if (confidence >= 60) buckets["60-69"] += 1;
    else buckets["50-59"] += 1;
  });
  return Object.entries(buckets).map(([Label, Value]) => ({ Label, Value }));
}

function sentimentInsight(counts, total) {
  if (!total) return "No sentiment rows available for this view.";
  const [leader, count] = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  const share = ((count / total) * 100).toFixed(1);
  if (leader === "Negative") return `${leader} leads at ${count.toLocaleString()} rows (${share}%). Prioritize the negative driver and repeat pain point cards below.`;
  if (leader === "Positive") return `${leader} leads at ${count.toLocaleString()} rows (${share}%). Use positives to identify repeatable behaviors.`;
  return `${leader} is the largest group at ${count.toLocaleString()} rows (${share}%). Review neutral verbatims for conversion opportunities.`;
}

function confidenceInsight(rows) {
  if (!rows.length) return "No confidence data available for this view.";
  const low = rows.filter((row) => Number(row["Confidence %"] || 0) < 70).length;
  const high = rows.filter((row) => Number(row["Confidence %"] || 0) >= 90).length;
  if (low) return `${low.toLocaleString()} rows are below 70% confidence. These are good candidates for manual review or override.`;
  return `${high.toLocaleString()} rows are at 90%+ confidence. The model is highly certain for most visible entries.`;
}

function detailForMetric(label, value, rows) {
  if (label === "Responses") return `Total responses equals the number of analyzed rows currently visible after filters: ${rows.length}.`;
  if (label === "Avg Confidence") return `Average confidence is calculated from the row-level Confidence % column: ${value}% across ${rows.length} visible rows.`;
  const count = rows.filter((row) => row.Sentiment === label).length;
  return `${label} is calculated as ${count} ${label.toLowerCase()} rows divided by ${rows.length} visible rows.`;
}

function showDetail(title, detail) {
  $("detailBody").innerHTML = `<h2>${escapeHtml(title)}</h2><div class="detail-content">${detail}</div>`;
  $("detailModal").classList.remove("hidden");
}

function renderInsights(insights) {
  const target = $("insightGrid");
  const smartCards = buildSmartInsightCards(state.filteredRows);
  const allInsights = [...smartCards, ...(insights || [])];
  if (!allInsights.length) {
    target.innerHTML = `<p>No verbatim insights available yet.</p>`;
    return;
  }
  target.innerHTML = allInsights.map((item) => {
    const evidence = Array.isArray(item.Evidence) && item.Evidence.length
      ? `<ul>${item.Evidence.slice(0, 5).map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul>`
      : "";
    const detail = item.DetailHtml || [
      item.Metric ? `<p><strong>Metric:</strong> ${escapeHtml(item.Metric)}</p>` : "",
      `<p><strong>Insight:</strong> ${escapeHtml(item.Insight || "")}</p>`,
      evidence ? `<h3>Evidence</h3>${evidence}` : "",
    ].join("");
    return `<div class="insight-card intelligence-card" tabindex="0" title="Double click for calculation and evidence" data-insight-title="${escapeHtml(item.Title)}"><span>${escapeHtml(item.Title)}</span><strong>${escapeHtml(item.Metric || "")}</strong><p>${escapeHtml(item.Insight)}</p>${evidence}<template>${detail}</template></div>`;
  }).join("");
  target.querySelectorAll(".insight-card").forEach((card) => {
    card.addEventListener("dblclick", () => showDetail(card.dataset.insightTitle || "Holistic Verbatim Intelligence", card.querySelector("template").innerHTML));
  });
}

function buildSmartInsightCards(rows) {
  if (!rows.length) return [];
  return [
    confidenceRiskCard(rows),
    negativeEscalationCard(rows),
    positiveStrengthCard(rows),
    sentimentByOwnerCard(rows),
    overrideAuditCard(rows),
    actionPriorityCard(rows),
  ].filter(Boolean);
}

function confidenceRiskCard(rows) {
  const lowRows = rows.filter((row) => Number(row["Confidence %"] || 0) < 70);
  const avgLow = lowRows.length ? Math.round(lowRows.reduce((sum, row) => sum + Number(row["Confidence %"] || 0), 0) / lowRows.length) : 0;
  const share = percent(lowRows.length, rows.length);
  return {
    Title: "Confidence Risk",
    Metric: `${lowRows.length.toLocaleString()} rows`,
    Insight: `${share} of visible rows are below 70% confidence and should be reviewed first.`,
    Evidence: lowRows.slice(0, 3).map((row) => `${row["Confidence %"]}% - ${row["Verbatim Feedback"]}`),
    DetailHtml: [
      `<p><strong>How the number is achieved:</strong> Rows where Confidence % is below 70 divided by all visible rows.</p>`,
      calculationLine("Low confidence rows", lowRows.length),
      calculationLine("Visible rows", rows.length),
      calculationLine("Risk share", share),
      calculationLine("Average confidence among risky rows", `${avgLow}%`),
      evidenceTable(lowRows, ["Verbatim Feedback", "Sentiment", "Confidence %", "Agent Name", "Manager/TL"], 12),
    ].join(""),
  };
}

function negativeEscalationCard(rows) {
  const negativeRows = rows.filter((row) => row.Sentiment === "Negative");
  const themes = topThemeCounts(negativeRows, 5);
  const top = themes[0];
  if (!top) {
    return {
      Title: "Negative Escalation Themes",
      Metric: "0 themes",
      Insight: "No negative rows are visible in the current view.",
      DetailHtml: `<p>No negative sentiment rows are currently visible after filters.</p>`,
    };
  }
  const matches = rowsForTheme(negativeRows, top.term);
  return {
    Title: "Negative Escalation Themes",
    Metric: `${top.term} (${top.count})`,
    Insight: `Top negative theme by repeated wording is "${top.term}".`,
    Evidence: themes.map((item) => `${item.term}: ${item.count}`),
    DetailHtml: [
      `<p><strong>How the number is achieved:</strong> Negative verbatims are tokenized, common stop words are removed, and repeated terms are counted.</p>`,
      calculationLine("Negative rows reviewed", negativeRows.length),
      calculationLine("Top theme count", `${top.count} rows containing "${top.term}"`),
      themeList(themes),
      evidenceTable(matches, ["Verbatim Feedback", "Sentiment", "Confidence %", "Agent Name", "Manager/TL"], 12),
    ].join(""),
  };
}

function positiveStrengthCard(rows) {
  const positiveRows = rows.filter((row) => row.Sentiment === "Positive");
  const themes = topThemeCounts(positiveRows, 5);
  const top = themes[0];
  if (!top) {
    return {
      Title: "Positive Strength Signals",
      Metric: "0 themes",
      Insight: "No positive rows are visible in the current view.",
      DetailHtml: `<p>No positive sentiment rows are currently visible after filters.</p>`,
    };
  }
  const matches = rowsForTheme(positiveRows, top.term);
  return {
    Title: "Positive Strength Signals",
    Metric: `${top.term} (${top.count})`,
    Insight: `The strongest positive signal is "${top.term}". Use it to identify behaviors worth repeating.`,
    Evidence: themes.map((item) => `${item.term}: ${item.count}`),
    DetailHtml: [
      `<p><strong>How the number is achieved:</strong> Positive verbatims are tokenized, common stop words are removed, and repeated terms are counted.</p>`,
      calculationLine("Positive rows reviewed", positiveRows.length),
      calculationLine("Top signal count", `${top.count} rows containing "${top.term}"`),
      themeList(themes),
      evidenceTable(matches, ["Verbatim Feedback", "Sentiment", "Confidence %", "Agent Name", "Manager/TL"], 12),
    ].join(""),
  };
}

function sentimentByOwnerCard(rows) {
  const agentGroups = groupSentimentRisk(rows, "Agent Name");
  const managerGroups = groupSentimentRisk(rows, "Manager/TL");
  const topAgent = agentGroups[0];
  const topManager = managerGroups[0];
  if (!topAgent && !topManager) {
    return {
      Title: "Sentiment by Agent / Manager",
      Metric: "Not mapped",
      Insight: "Map agent or manager fields to compare sentiment ownership.",
      DetailHtml: `<p>Agent and manager columns are not available in the analyzed result table.</p>`,
    };
  }
  const leader = topAgent || topManager;
  const leaderRows = rows.filter((row) => String(row[leader.column] || "") === leader.name);
  return {
    Title: "Sentiment by Agent / Manager",
    Metric: `${leader.name}`,
    Insight: `${leader.name} has the highest visible negative concentration among mapped owner fields.`,
    Evidence: [
      topAgent ? `Agent: ${topAgent.name} - ${topAgent.negative}/${topAgent.total} negative (${topAgent.rate})` : "",
      topManager ? `Manager/TL: ${topManager.name} - ${topManager.negative}/${topManager.total} negative (${topManager.rate})` : "",
    ].filter(Boolean),
    DetailHtml: [
      `<p><strong>How the number is achieved:</strong> Rows are grouped by Agent Name and Manager/TL. Negative concentration equals negative rows divided by total rows for that owner. Groups with fewer than 2 rows are deprioritized.</p>`,
      topAgent ? calculationLine("Top agent", `${topAgent.name}: ${topAgent.negative}/${topAgent.total} = ${topAgent.rate}`) : "",
      topManager ? calculationLine("Top manager/TL", `${topManager.name}: ${topManager.negative}/${topManager.total} = ${topManager.rate}`) : "",
      ownerTable("Agent Name", agentGroups),
      ownerTable("Manager/TL", managerGroups),
      evidenceTable(leaderRows, ["Verbatim Feedback", "Sentiment", "Confidence %", leader.column], 10),
    ].join(""),
  };
}

function overrideAuditCard(rows) {
  const overridden = rows.filter((row) => row["Review Status"] === "Overridden");
  const share = percent(overridden.length, rows.length);
  const transitions = transitionCounts(overridden);
  return {
    Title: "Override Audit",
    Metric: `${overridden.length.toLocaleString()} overrides`,
    Insight: `${share} of visible rows have been manually overridden.`,
    Evidence: Object.entries(transitions).slice(0, 3).map(([label, count]) => `${label}: ${count}`),
    DetailHtml: [
      `<p><strong>How the number is achieved:</strong> Rows where Review Status equals Overridden are counted and divided by all visible rows.</p>`,
      calculationLine("Overridden rows", overridden.length),
      calculationLine("Visible rows", rows.length),
      calculationLine("Override share", share),
      transitionTable(transitions),
      evidenceTable(overridden, ["Verbatim Feedback", "Original Sentiment", "Sentiment", "Confidence %"], 12),
    ].join(""),
  };
}

function actionPriorityCard(rows) {
  const negativeRows = rows.filter((row) => row.Sentiment === "Negative");
  const themes = topThemeCounts(negativeRows, 1);
  const top = themes[0];
  const lowNegative = negativeRows.filter((row) => Number(row["Confidence %"] || 0) < 70);
  const matches = top ? rowsForTheme(negativeRows, top.term) : [];
  const priorityRows = uniqueRows([...matches, ...lowNegative]);
  const score = priorityRows.length;
  return {
    Title: "Action Priority",
    Metric: `${score.toLocaleString()} rows`,
    Insight: top ? `Start with negative "${top.term}" rows and low-confidence negative entries.` : "No negative priority cluster is visible right now.",
    Evidence: [
      top ? `Repeat negative theme: ${top.term} (${top.count})` : "",
      `Low-confidence negative rows: ${lowNegative.length}`,
      `Unique priority rows: ${score}`,
    ].filter(Boolean),
    DetailHtml: [
      `<p><strong>How the number is achieved:</strong> Priority rows are the unique union of the top repeated negative theme and negative rows below 70% confidence.</p>`,
      top ? calculationLine("Top negative theme rows", `${top.count} rows containing "${top.term}"`) : calculationLine("Top negative theme rows", 0),
      calculationLine("Low-confidence negative rows", lowNegative.length),
      calculationLine("Unique priority rows", score),
      evidenceTable(priorityRows, ["Verbatim Feedback", "Sentiment", "Confidence %", "Agent Name", "Manager/TL"], 12),
    ].join(""),
  };
}

function topThemeCounts(rows, limit = 5) {
  const counts = new Map();
  rows.forEach((row) => {
    const uniqueTerms = new Set(tokensFor(row["Verbatim Feedback"]));
    uniqueTerms.forEach((term) => counts.set(term, (counts.get(term) || 0) + 1));
  });
  return [...counts.entries()]
    .map(([term, count]) => ({ term, count }))
    .sort((a, b) => b.count - a.count || a.term.localeCompare(b.term))
    .slice(0, limit);
}

function rowsForTheme(rows, term) {
  const needle = String(term || "").toLowerCase();
  return rows.filter((row) => tokensFor(row["Verbatim Feedback"]).includes(needle));
}

function groupSentimentRisk(rows, column) {
  const groups = new Map();
  rows.forEach((row) => {
    const name = String(row[column] || "").trim();
    if (!name || name === "No Value") return;
    if (!groups.has(name)) groups.set(name, { name, column, total: 0, negative: 0 });
    const group = groups.get(name);
    group.total += 1;
    if (row.Sentiment === "Negative") group.negative += 1;
  });
  return [...groups.values()]
    .map((group) => ({ ...group, rateValue: group.total ? group.negative / group.total : 0, rate: percent(group.negative, group.total) }))
    .sort((a, b) => (b.total >= 2) - (a.total >= 2) || b.rateValue - a.rateValue || b.negative - a.negative || b.total - a.total)
    .slice(0, 8);
}

function transitionCounts(rows) {
  return rows.reduce((acc, row) => {
    const from = row["Original Sentiment"] || "Original not captured";
    const to = row.Sentiment || "No sentiment";
    const key = `${from} -> ${to}`;
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function uniqueRows(rows) {
  const seen = new Set();
  return rows.filter((row) => {
    const id = row.__row_id ?? row["Verbatim Feedback"];
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

function calculationLine(label, value) {
  return `<div class="calc-line"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function themeList(themes) {
  if (!themes.length) return "";
  return `<h3>Theme Counts</h3><div class="detail-list">${themes.map((item) => calculationLine(item.term, `${item.count} rows`)).join("")}</div>`;
}

function ownerTable(title, groups) {
  if (!groups.length) return "";
  return `<h3>${escapeHtml(title)}</h3><table class="detail-table"><thead><tr><th>Name</th><th>Total Rows</th><th>Negative Rows</th><th>Negative %</th></tr></thead><tbody>${groups.map((group) => `<tr><td>${escapeHtml(group.name)}</td><td>${escapeHtml(group.total)}</td><td>${escapeHtml(group.negative)}</td><td>${escapeHtml(group.rate)}</td></tr>`).join("")}</tbody></table>`;
}

function transitionTable(transitions) {
  const entries = Object.entries(transitions);
  if (!entries.length) return `<p>No override transitions are visible yet.</p>`;
  return `<h3>Override Transitions</h3><table class="detail-table"><thead><tr><th>Transition</th><th>Rows</th></tr></thead><tbody>${entries.map(([label, count]) => `<tr><td>${escapeHtml(label)}</td><td>${escapeHtml(count)}</td></tr>`).join("")}</tbody></table>`;
}

function evidenceTable(rows, columns, limit = 10) {
  if (!rows.length) return `<p>No supporting rows are visible for this card.</p>`;
  const visibleRows = rows.slice(0, limit);
  return `<h3>Supporting Rows</h3><p class="detail-note">Showing ${visibleRows.length.toLocaleString()} of ${rows.length.toLocaleString()} matching rows.</p><table class="detail-table"><thead><tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join("")}</tr></thead><tbody>${visibleRows.map((row) => `<tr>${columns.map((col) => `<td>${escapeHtml(row[col] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function renderRowsTable() {
  const tables = [$("dashboardRowsTable"), $("rowsTable")].filter(Boolean);
  const rows = state.filteredRows;
  if (!rows.length) {
    tables.forEach((table) => { table.innerHTML = ""; });
    return;
  }
  const columns = ["S.No", "Verbatim Feedback", "Sentiment", "Confidence %", "Sentiment Score", "Sentiment Mode", "Analysis Source", "Review Status", "Agent Name", "Manager/TL", "Feedback Date"];
  const html = `<thead><tr>${columns.map((col) => `<th><span class="cell-wrap">${escapeHtml(col)}</span></th>`).join("")}</tr></thead><tbody>${rows.map((row, index) => `<tr data-row-index="${index}" class="${row["Review Status"] ? "overridden-row" : ""}" title="Double click to review and override">${columns.map((col) => `<td>${renderTableCell(col, col === "S.No" ? index + 1 : row[col])}</td>`).join("")}</tr>`).join("")}</tbody>`;
  tables.forEach((table) => { table.innerHTML = html; });
}

function renderTableCell(column, value) {
  if (column === "S.No") {
    return `<span class="serial-cell">${escapeHtml(value)}</span>`;
  }
  if (column === "Sentiment") {
    const sentiment = String(value || "Neutral");
    return `<span class="sentiment-pill ${sentiment.toLowerCase()}">${escapeHtml(sentiment)}</span>`;
  }
  if (column === "Confidence %") {
    const score = Number(value || 0);
    const band = score >= 90 ? "high" : score >= 70 ? "medium" : "low";
    return `<span class="confidence-pill ${band}">${escapeHtml(score)}%</span>`;
  }
  if (column === "Review Status" && value) {
    return `<span class="review-pill">${escapeHtml(value)}</span>`;
  }
  return `<span class="cell-wrap" title="${escapeHtml(value)}">${escapeHtml(value)}</span>`;
}

function openRowReview(index) {
  state.selectedRowIndex = Math.max(0, Math.min(index, state.filteredRows.length - 1));
  const row = state.filteredRows[state.selectedRowIndex];
  if (!row) return;
  $("rowReviewBody").innerHTML = `
    <h2>Review Entry ${state.selectedRowIndex + 1} of ${state.filteredRows.length}</h2>
    <div class="review-verbatim">${escapeHtml(row["Verbatim Feedback"])}</div>
    <div class="review-grid">
      <div><span>Current Sentiment</span><strong>${escapeHtml(row.Sentiment)}</strong></div>
      <div><span>Confidence</span><strong>${escapeHtml(row["Confidence %"])}%</strong></div>
      <div><span>Status</span><strong>${escapeHtml(row["Review Status"] || "Original")}</strong></div>
    </div>
    <label>Override Sentiment<select id="overrideSentiment"><option value="Positive">Positive</option><option value="Neutral">Neutral</option><option value="Negative">Negative</option></select></label>
    <div class="modal-actions">
      <button class="secondary" type="button" data-review-prev>Back</button>
      <button class="primary compact-action" type="button" data-review-override>Override</button>
      <button class="secondary" type="button" data-review-next>Next</button>
    </div>
  `;
  $("overrideSentiment").value = row.Sentiment || "Neutral";
  $("rowModal").classList.remove("hidden");
}

function overrideCurrentRow() {
  const row = state.filteredRows[state.selectedRowIndex];
  if (!row) return;
  const selected = $("overrideSentiment").value;
  if (!row["Original Sentiment"]) row["Original Sentiment"] = row.Sentiment || "Neutral";
  row.Sentiment = selected;
  row["Review Status"] = "Overridden";
  const original = state.rows.find((item) => item.__row_id === row.__row_id);
  if (original) {
    if (!original["Original Sentiment"]) original["Original Sentiment"] = original.Sentiment || "Neutral";
    original.Sentiment = selected;
    original["Review Status"] = "Overridden";
  }
  applyFilters();
  renderResults(state.last);
  renderWordCloud();
  openRowReview(Math.min(state.selectedRowIndex, state.filteredRows.length - 1));
}

function renderWordCloud() {
  const target = $("wordCloud");
  const rows = state.rows;
  const entries = cloudEntries(rows, state.cloudMode).slice(0, 80);
  if (!entries.length) {
    target.innerHTML = `<p>No word cloud terms available.</p>`;
    renderWordCloudInsights([]);
    return;
  }
  const max = Math.max(...entries.map((item) => item.count), 1);
  target.innerHTML = entries.map((item) => {
    const size = 14 + Math.round((item.count / max) * 24);
    return `<button type="button" style="font-size:${size}px" data-cloud-term="${escapeHtml(item.term)}" title="${item.count} matching entries">${escapeHtml(item.term)}</button>`;
  }).join("");
  renderWordCloudInsights(entries);
}

function cloudEntries(rows, cloudMode) {
  const counts = new Map();
  rows.forEach((row) => {
    const tokens = tokensFor(row["Verbatim Feedback"]);
    const source = cloudMode === "dual" ? bigrams(tokens) : tokens;
    source.forEach((term) => {
      const weight = cloudMode === "insights" && row.Sentiment === "Negative" ? 2 : 1;
      counts.set(term, (counts.get(term) || 0) + weight);
    });
  });
  return [...counts.entries()].map(([term, count]) => ({ term, count })).sort((a, b) => b.count - a.count);
}

function tokensFor(text) {
  const stop = new Set(["the", "and", "for", "that", "this", "with", "was", "were", "you", "your", "are", "not", "but", "have", "had", "from", "they", "them", "our", "out", "too", "very"]);
  return String(text || "").toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter((word) => word.length > 2 && !stop.has(word));
}

function bigrams(tokens) {
  const pairs = [];
  for (let i = 0; i < tokens.length - 1; i += 1) pairs.push(`${tokens[i]} ${tokens[i + 1]}`);
  return pairs;
}

function showWordMatches(term) {
  const matches = state.rows.filter((row) => String(row["Verbatim Feedback"] || "").toLowerCase().includes(term.toLowerCase()));
  $("wordModalBody").innerHTML = `<h2>${escapeHtml(term)}</h2><p>${matches.length} matching verbatims</p><div class="verbatim-list">${matches.map((row) => `<div><span>${escapeHtml(row.Sentiment)} Â· ${escapeHtml(row["Confidence %"])}%</span><p>${escapeHtml(row["Verbatim Feedback"])}</p></div>`).join("")}</div>`;
  $("wordModal").classList.remove("hidden");
}

function renderWordCloudInsights(entries) {
  renderWordMetricCards(entries);
  renderBar("wordTopTermsChart", entries.slice(0, 10).map((item) => ({ Label: item.term, Value: item.count })), "#00a7a7", {
    noteId: "wordTopTermsNote",
    note: entries[0] ? `"${entries[0].term}" is the most repeated language signal with ${entries[0].count.toLocaleString()} mentions.` : "Run analysis to view top language signals.",
  });
  const negativeEntries = cloudEntries(state.rows.filter((row) => row.Sentiment === "Negative"), state.cloudMode);
  renderBar("negativeTermsChart", negativeEntries.slice(0, 10).map((item) => ({ Label: item.term, Value: item.count })), "#d94045", {
    noteId: "negativeTermsNote",
    note: negativeEntries[0] ? `"${negativeEntries[0].term}" is the leading negative language signal. Double-check matching verbatims before actioning.` : "No negative terms are available in this view.",
  });
  renderTermSentimentChart(entries.slice(0, 7));
  renderWordEvidenceTable(entries.slice(0, 12));
}

function renderWordMetricCards(entries) {
  const target = $("wordMetricGrid");
  if (!target) return;
  const totalTerms = entries.reduce((sum, item) => sum + item.count, 0);
  const top = entries[0];
  const negativeTop = cloudEntries(state.rows.filter((row) => row.Sentiment === "Negative"), state.cloudMode)[0];
  const positiveTop = cloudEntries(state.rows.filter((row) => row.Sentiment === "Positive"), state.cloudMode)[0];
  const cards = [
    ["Unique Signals", entries.length.toLocaleString(), "terms shown in current cloud"],
    ["Total Mentions", totalTerms.toLocaleString(), "weighted mentions in current mode"],
    ["Top Signal", top ? top.term : "None", top ? `${top.count} mentions` : "no signal yet"],
    ["Negative Signal", negativeTop ? negativeTop.term : "None", negativeTop ? `${negativeTop.count} mentions` : "no negative signal"],
    ["Positive Signal", positiveTop ? positiveTop.term : "None", positiveTop ? `${positiveTop.count} mentions` : "no positive signal"],
  ];
  target.innerHTML = cards.map(([label, value, note]) => `<div class="metric-card compact-metric"><div class="metric-card-main"><div class="metric-icon">AI</div><div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></div></div></div>`).join("");
}

function renderTermSentimentChart(entries) {
  const svg = $("termSentimentChart");
  if (!svg) return;
  if (!entries.length) {
    svg.innerHTML = `<text x="380" y="130" text-anchor="middle" fill="#728399">No term sentiment data yet.</text>`;
    if ($("termSentimentNote")) $("termSentimentNote").textContent = "Run analysis to view language sentiment mix.";
    return;
  }
  const left = 150, top = 28, rowH = 36, width = 500;
  const height = top + entries.length * rowH + 30;
  svg.setAttribute("viewBox", `0 0 760 ${height}`);
  svg.style.height = `${height}px`;
  const bars = entries.map((entry, index) => {
    const rows = rowsForTerm(state.rows, entry.term);
    const counts = sentimentCounts(rows);
    const total = Math.max(rows.length, 1);
    const positiveW = (counts.Positive / total) * width;
    const neutralW = (counts.Neutral / total) * width;
    const negativeW = (counts.Negative / total) * width;
    const y = top + index * rowH;
    const label = entry.term.length > 18 ? `${entry.term.slice(0, 16)}...` : entry.term;
    return `<text class="bar-label" x="${left - 12}" y="${y + 17}" text-anchor="end">${escapeHtml(label)}</text><rect x="${left}" y="${y}" width="${width}" height="18" rx="9" fill="#eef4f8"></rect><rect x="${left}" y="${y}" width="${positiveW}" height="18" rx="9" fill="#00a86b"></rect><rect x="${left + positiveW}" y="${y}" width="${neutralW}" height="18" fill="#7893aa"></rect><rect x="${left + positiveW + neutralW}" y="${y}" width="${negativeW}" height="18" rx="9" fill="#d94045"></rect><text class="bar-value" x="${left + width + 10}" y="${y + 14}">${counts.Positive}/${counts.Neutral}/${counts.Negative}</text>`;
  }).join("");
  svg.innerHTML = `${bars}<text x="${left}" y="18" class="bar-label" fill="#00a86b">Positive</text><text x="${left + 80}" y="18" class="bar-label" fill="#7893aa">Neutral</text><text x="${left + 155}" y="18" class="bar-label" fill="#d94045">Negative</text>`;
  if ($("termSentimentNote")) $("termSentimentNote").textContent = "Each bar splits matching verbatims into Positive / Neutral / Negative counts.";
}

function renderWordEvidenceTable(entries) {
  const table = $("wordEvidenceTable");
  if (!table) return;
  if (!entries.length) {
    table.innerHTML = "";
    return;
  }
  const rows = entries.map((entry, index) => {
    const matches = rowsForTerm(state.rows, entry.term);
    const counts = sentimentCounts(matches);
    const sample = matches[0]?.["Verbatim Feedback"] || "";
    return { index: index + 1, term: entry.term, mentions: entry.count, positive: counts.Positive, neutral: counts.Neutral, negative: counts.Negative, sample };
  });
  table.innerHTML = `<thead><tr><th>S.No</th><th>Term</th><th>Mentions</th><th>Positive</th><th>Neutral</th><th>Negative</th><th>Sample Verbatim</th></tr></thead><tbody>${rows.map((row) => `<tr data-cloud-term="${escapeHtml(row.term)}"><td>${row.index}</td><td>${escapeHtml(row.term)}</td><td>${row.mentions}</td><td>${row.positive}</td><td>${row.neutral}</td><td>${row.negative}</td><td><span class="cell-wrap" title="${escapeHtml(row.sample)}">${escapeHtml(row.sample)}</span></td></tr>`).join("")}</tbody>`;
}

function rowsForTerm(rows, term) {
  const normalized = String(term || "").toLowerCase();
  if (!normalized) return [];
  if (normalized.includes(" ")) {
    return rows.filter((row) => String(row["Verbatim Feedback"] || "").toLowerCase().includes(normalized));
  }
  return rows.filter((row) => tokensFor(row["Verbatim Feedback"]).includes(normalized));
}

function requireAnalysis() {
  if (!state.last || !state.rows.length) {
    alert("Run Perform Sentiment Analysis before exporting.");
    return false;
  }
  return true;
}

function csvEscape(value) {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function exportCsv() {
  if (!requireAnalysis()) return;
  const columns = ["S.No", "Verbatim Feedback", "Sentiment", "Confidence %", "Sentiment Score", "Sentiment Mode", "Analysis Source", "Review Status", "Agent Name", "Manager/TL", "Feedback Date"];
  const csv = "\ufeff" + [columns.join(","), ...state.rows.map((row, index) => columns.map((col) => csvEscape(col === "S.No" ? index + 1 : row[col])).join(","))].join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `sentiment-analysis-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  URL.revokeObjectURL(link.href);
  link.remove();
}

function tableHtml(rows) {
  if (!rows.length) return "<p>No rows available.</p>";
  const columns = ["S.No", "Verbatim Feedback", "Sentiment", "Confidence %", "Sentiment Score", "Sentiment Mode", "Analysis Source", "Review Status", "Agent Name", "Manager/TL", "Feedback Date"];
  return `<table><thead><tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join("")}</tr></thead><tbody>${rows.map((row, index) => `<tr>${columns.map((col) => `<td>${escapeHtml(col === "S.No" ? index + 1 : row[col])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function exportPdf() {
  if (!requireAnalysis()) return;
  const rows = state.filteredRows.length ? state.filteredRows : state.rows;
  const counts = sentimentCounts(rows);
  const insights = [...buildSmartInsightCards(rows), ...((state.last.intelligenceCards || state.last.insights || []))];
  const report = window.open("", "_blank");
  if (!report) {
    alert("Allow pop-ups to export the PDF.");
    return;
  }
  const metrics = [
    ["Responses", rows.length],
    ["Positive", `${counts.Positive} (${percent(counts.Positive, rows.length)})`],
    ["Neutral", `${counts.Neutral} (${percent(counts.Neutral, rows.length)})`],
    ["Negative", `${counts.Negative} (${percent(counts.Negative, rows.length)})`],
    ["Avg Confidence", `${averageConfidence(rows)}%`],
  ];
  report.document.write(`
    <!doctype html>
    <html>
      <head>
        <title>Sentiment Analysis Export</title>
        <style>
          @page{size:A4 landscape;margin:10mm}
          body{font-family:Segoe UI,Arial,sans-serif;color:#0c2845;margin:0;background:#fff;font-size:11px}
          header{display:flex;justify-content:space-between;gap:18px;border-bottom:4px solid #00a7a7;margin-bottom:14px;padding-bottom:10px}
          h1{margin:0;font-size:24px} h2{margin:18px 0 8px;font-size:16px;color:#0c2845}
          .meta{color:#73869a;margin-top:6px}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0}
          .metric{border:1px solid #cbd8e5;border-top:4px solid #00a7a7;border-radius:8px;padding:9px;background:#fbfdff}
          .metric span{display:block;color:#73869a;font-size:10px;text-transform:uppercase}.metric strong{display:block;font-size:18px;margin-top:5px;font-weight:400}
          .insights{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.insight{border:1px solid #dce6ef;border-left:4px solid #00a7a7;border-radius:7px;padding:8px;page-break-inside:avoid}
          .insight strong{display:block;margin-bottom:4px}.insight span{color:#73869a}
          table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:8.5px;margin-top:8px;page-break-inside:auto}
          thead{display:table-header-group} tr{page-break-inside:avoid;page-break-after:auto}
          th{background:#edf3f7;text-align:left;color:#29465f}
          th,td{border:1px solid #dce6ef;padding:4px;vertical-align:top;white-space:pre-wrap;overflow:visible;text-overflow:clip;word-break:break-word}
          td:nth-child(1),th:nth-child(1){width:28px;text-align:center}
          td:nth-child(2),th:nth-child(2){width:31%}
          td:nth-child(3),th:nth-child(3){width:58px}
          td:nth-child(4),th:nth-child(4){width:62px}
          td:nth-child(5),th:nth-child(5){width:64px}
          .section{page-break-inside:auto}.small{color:#73869a;font-size:10px}@media print{button{display:none}}
        </style>
      </head>
      <body>
        <header><h1>Sentiment Analysis Export</h1><div class="meta">${escapeHtml(state.file?.name || "Uploaded file")} Â· ${engineLabel($("sentimentEngine").value)} Â· ${new Date().toLocaleString()}</div></header>
        <section class="section"><h2>Summary</h2><div class="metrics">${metrics.map(([label, value]) => `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</div></section>
        <section class="section"><h2>Holistic Verbatim Intelligence</h2>${((state.last.intelligenceCards || state.last.insights || [])).map((item) => `<p><strong>${escapeHtml(item.Title)}</strong>${item.Metric ? ` - ${escapeHtml(item.Metric)}` : ""}: ${escapeHtml(item.Insight)}</p>`).join("") || "<p>No insights available.</p>"}</section>
        <section class="section"><h2>Analyzed Rows</h2><p class="small">Showing all ${rows.length.toLocaleString()} rows with full cell text.</p>${tableHtml(rows)}</section>
        <script>window.onload=()=>{window.print();};</script>
      </body>
    </html>
  `);
  report.document.close();
}

function exportPdfEnhanced() {
  if (!requireAnalysis()) return;
  const rows = state.filteredRows.length ? state.filteredRows : state.rows;
  const counts = sentimentCounts(rows);
  const insights = [...buildSmartInsightCards(rows), ...((state.last.intelligenceCards || state.last.insights || []))];
  const report = window.open("", "_blank");
  if (!report) {
    alert("Allow pop-ups to export the PDF.");
    return;
  }
  const metrics = [
    ["Responses", rows.length],
    ["Positive", `${counts.Positive} (${percent(counts.Positive, rows.length)})`],
    ["Neutral", `${counts.Neutral} (${percent(counts.Neutral, rows.length)})`],
    ["Negative", `${counts.Negative} (${percent(counts.Negative, rows.length)})`],
    ["Avg Confidence", `${averageConfidence(rows)}%`],
  ];
  const runItems = runDetailItems();
  const charts = [
    chartExportSection("sentimentChart", "Sentiment Mix", "sentimentChartNote"),
    chartExportSection("confidenceChart", "Confidence Distribution", "confidenceChartNote"),
    chartExportSection("ownerSentimentChart", "Sentiment by Owner", "ownerSentimentChartNote"),
    chartExportSection("sentimentTrendChart", "Sentiment Trend", "sentimentTrendChartNote"),
    chartExportSection("wordTopTermsChart", "Top Language Terms", "wordTopTermsNote"),
    chartExportSection("negativeTermsChart", "Negative Language Signals", "negativeTermsNote"),
    chartExportSection("termSentimentChart", "Language by Sentiment", "termSentimentNote"),
  ].filter(Boolean).join("");
  report.document.write(`
    <!doctype html>
    <html>
      <head>
        <title>Sentiment Analysis Export</title>
        <style>
          @page{size:A4 landscape;margin:10mm}
          body{font-family:Segoe UI,Arial,sans-serif;color:#0c2845;margin:0;background:#fff;font-size:11px}
          header{display:flex;justify-content:space-between;gap:18px;border-bottom:4px solid #00a7a7;margin-bottom:14px;padding-bottom:10px}
          h1{margin:0;font-size:24px} h2{margin:18px 0 8px;font-size:16px;color:#0c2845} h3{margin:0 0 6px;font-size:14px}
          a{color:#007676;text-decoration:none}.meta,.small{color:#73869a}.index{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0 18px}
          .index a,.run div,.metric,.insight,.chart-box{border:1px solid #dce6ef;border-radius:8px;background:#fbfdff;padding:9px}
          .run{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.run span,.metric span{display:block;color:#73869a;font-size:10px;text-transform:uppercase}.run strong,.metric strong{display:block;margin-top:5px;font-weight:400}
          .metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0}.metric{border-top:4px solid #00a7a7}.metric strong{font-size:18px}
          .insights{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.insight{border-left:4px solid #00a7a7;page-break-inside:avoid}.insight strong{display:block;margin-bottom:4px}.insight span{color:#73869a}
          .chart-grid-print{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.chart-box{page-break-inside:avoid}.chart-box svg{width:100%;height:auto;max-height:260px}.chart-note-print{margin-top:6px;color:#5f7284;font-size:10px}
          table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:8.5px;margin-top:8px;page-break-inside:auto}thead{display:table-header-group}tr{page-break-inside:avoid;page-break-after:auto}
          th{background:#edf3f7;text-align:left;color:#29465f}th,td{border:1px solid #dce6ef;padding:4px;vertical-align:top;white-space:pre-wrap;overflow:visible;text-overflow:clip;word-break:break-word}
          td:nth-child(1),th:nth-child(1){width:28px;text-align:center}td:nth-child(2),th:nth-child(2){width:31%}td:nth-child(3),th:nth-child(3){width:58px}td:nth-child(4),th:nth-child(4){width:62px}td:nth-child(5),th:nth-child(5){width:64px}
          .page{page-break-after:always}.section{page-break-inside:auto}@media print{button{display:none}}
        </style>
      </head>
      <body>
        <section id="index" class="page">
          <header><div><h1>Sentiment Analysis Export</h1><div class="meta">${escapeHtml(state.file?.name || "Uploaded file")}</div></div><div class="meta">${engineLabel($("sentimentEngine").value)}<br>${new Date().toLocaleString()}<br>${rows.length.toLocaleString()} rows</div></header>
          <h2>Index</h2>
          <div class="index"><a href="#run">Run Details</a><a href="#summary">Summary</a><a href="#charts">Charts</a><a href="#insights">Holistic Intelligence</a><a href="#rows">Analyzed Rows</a></div>
          <h2 id="run">Run Details</h2>
          <div class="run">${runItems.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</div>
          <h2 id="summary">Summary</h2>
          <div class="metrics">${metrics.map(([label, value]) => `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</div>
        </section>
        <section id="charts" class="page"><h2>Charts and Graphs</h2><div class="chart-grid-print">${charts || "<p>No charts available.</p>"}</div></section>
        <section id="insights" class="page"><h2>Holistic Verbatim Intelligence</h2><div class="insights">${insights.map((item) => `<div class="insight"><strong>${escapeHtml(item.Title)}</strong>${item.Metric ? `<span>${escapeHtml(item.Metric)}</span>` : ""}<p>${escapeHtml(item.Insight || "")}</p></div>`).join("") || "<p>No insights available.</p>"}</div></section>
        <section id="rows" class="section"><h2>Analyzed Rows</h2><p class="small">Showing all ${rows.length.toLocaleString()} rows with full cell text.</p>${tableHtml(rows)}</section>
        <script>window.onload=()=>{window.print();};</script>
      </body>
    </html>
  `);
  report.document.close();
}

function runDetailItems() {
  const run = state.run || {};
  return [
    ["Started", run.startedAt ? formatDateTime(run.startedAt) : ""],
    ["Ended", run.endedAt ? formatDateTime(run.endedAt) : ""],
    ["Duration", run.durationMs ? formatDuration(run.durationMs) : ""],
    ["Mode", run.mode || engineLabel($("sentimentEngine").value)],
    ["Rows", Number(run.rows || state.rows.length || 0).toLocaleString()],
    ["File", run.fileName || state.file?.name || ""],
    ["Verbatim Field", run.feedbackColumn || $("feedbackCol")?.value || ""],
    ["Status", run.status || "Completed"],
  ];
}

function chartExportSection(svgId, title, noteId) {
  const svg = $(svgId);
  if (!svg || !svg.innerHTML.trim()) return "";
  const clone = svg.cloneNode(true);
  clone.removeAttribute("style");
  clone.setAttribute("preserveAspectRatio", "xMidYMid meet");
  const note = noteId && $(noteId) ? $(noteId).textContent : "";
  return `<div class="chart-box"><h3>${escapeHtml(title)}</h3>${clone.outerHTML}<div class="chart-note-print">${escapeHtml(note)}</div></div>`;
}

function renderBar(svgId, rows, color, options = {}) {
  const svg = $(svgId);
  if (!svg) return;
  const data = (rows || []).filter((row) => row.Label !== undefined).slice(0, 10);
  if (!data.length) {
    svg.setAttribute("viewBox", "0 0 760 300");
    svg.style.height = "300px";
    svg.innerHTML = `<text x="380" y="130" text-anchor="middle" fill="#728399">No data yet.</text>`;
    return;
  }
  const max = Math.max(...data.map((row) => Number(row.Value || 0)), 1);
  const total = data.reduce((sum, row) => sum + Number(row.Value || 0), 0);
  const left = 180, top = 34, rowH = 40, width = 500;
  const svgHeight = Math.max(300, top + data.length * rowH + 52);
  svg.setAttribute("viewBox", `0 0 760 ${svgHeight}`);
  svg.style.height = `${svgHeight}px`;
  const grid = [0, .25, .5, .75, 1].map((ratio) => {
    const x = left + ratio * width;
    return `<line x1="${x}" y1="18" x2="${x}" y2="${top + data.length * rowH + 4}" stroke="#edf3f7" stroke-width="1"></line>`;
  }).join("");
  const bars = data.map((row, index) => {
    const y = top + index * rowH;
    const value = Number(row.Value || 0);
    const w = Math.max(4, (value / max) * width);
    const label = String(row.Label || "").length > 24 ? `${String(row.Label).slice(0, 22)}...` : String(row.Label || "");
    const fill = options.palette?.[index] || color;
    const share = total ? ` (${((value / total) * 100).toFixed(1)}%)` : "";
    const valueText = `${Number(value).toFixed(value % 1 ? 1 : 0)}${options.suffix || ""}${share}`;
    return `<text class="bar-label" x="${left - 14}" y="${y + 17}" text-anchor="end">${escapeHtml(label)}</text><rect x="${left}" y="${y}" width="${width}" height="20" rx="10" fill="#eef4f8"></rect><rect x="${left}" y="${y}" width="${w}" height="20" rx="10" fill="${fill}"></rect><circle cx="${left}" cy="${y + 10}" r="4" fill="${fill}"></circle><text class="bar-value" x="${Math.min(left + w + 10, 730)}" y="${y + 15}">${escapeHtml(valueText)}</text>`;
  }).join("");
  svg.innerHTML = `${grid}${bars}<line x1="${left}" y1="${top + data.length * rowH + 2}" x2="${left + width}" y2="${top + data.length * rowH + 2}" stroke="#dce6ef" stroke-width="1"></line>`;
  if (options.noteId && $(options.noteId)) $(options.noteId).textContent = options.note || "";
}

function renderOwnerSentimentChart(rows) {
  const svg = $("ownerSentimentChart");
  if (!svg) return;
  const agentGroups = groupSentimentRisk(rows, "Agent Name");
  const managerGroups = groupSentimentRisk(rows, "Manager/TL");
  const source = agentGroups.length ? agentGroups : managerGroups;
  const sourceLabel = agentGroups.length ? "Agent Name" : "Manager/TL";
  const data = source.slice(0, 8).map((group) => ({
    Label: group.name,
    Value: Number((group.rateValue * 100).toFixed(1)),
    Count: `${group.negative}/${group.total}`,
  }));
  if (!data.length) {
    svg.innerHTML = `<text x="380" y="130" text-anchor="middle" fill="#728399">Map Agent or Manager to show this chart.</text>`;
    if ($("ownerSentimentChartNote")) $("ownerSentimentChartNote").textContent = "No owner field is mapped in the current analysis.";
    return;
  }
  renderBar("ownerSentimentChart", data, "#d94045", { suffix: "%", noteId: "ownerSentimentChartNote", note: ownerSentimentInsight(data, sourceLabel) });
}

function ownerSentimentInsight(data, sourceLabel) {
  const top = data[0];
  if (!top) return "No owner concentration available.";
  return `${top.Label} has the highest negative concentration at ${top.Value}% using ${sourceLabel}. Use this with row evidence before coaching or escalation.`;
}

function renderSentimentTrendChart(rows) {
  const svg = $("sentimentTrendChart");
  if (!svg) return;
  const trend = sentimentTrendRows(rows);
  if (trend.length < 2) {
    svg.innerHTML = `<text x="380" y="130" text-anchor="middle" fill="#728399">Map Feedback Date to show trend.</text>`;
    if ($("sentimentTrendChartNote")) $("sentimentTrendChartNote").textContent = "A mapped date field is needed for trend analysis.";
    return;
  }
  const width = 600, height = 210, left = 80, top = 30;
  const max = Math.max(...trend.map((item) => Math.max(item.positivePct, item.negativePct)), 1);
  const step = trend.length > 1 ? width / (trend.length - 1) : width;
  const yFor = (value) => top + height - (value / max) * height;
  const xFor = (index) => left + index * step;
  const grid = [0, .25, .5, .75, 1].map((ratio) => {
    const y = top + height - ratio * height;
    return `<line x1="${left}" y1="${y}" x2="${left + width}" y2="${y}" stroke="#edf3f7"></line><text x="${left - 12}" y="${y + 4}" text-anchor="end" class="bar-label">${Math.round(ratio * max)}%</text>`;
  }).join("");
  const linePath = (key) => trend.map((item, index) => `${index ? "L" : "M"}${xFor(index)},${yFor(item[key])}`).join(" ");
  const points = (key, color) => trend.map((item, index) => `<circle cx="${xFor(index)}" cy="${yFor(item[key])}" r="4" fill="#fff" stroke="${color}" stroke-width="3"><title>${escapeHtml(item.Label)}: ${item[key]}%</title></circle>`).join("");
  const labels = trend.map((item, index) => `<text x="${xFor(index)}" y="${top + height + 24}" text-anchor="middle" class="bar-label">${escapeHtml(shortDateLabel(item.Label))}</text>`).join("");
  svg.innerHTML = `
    ${grid}
    <path d="${linePath("positivePct")}" fill="none" stroke="#00a7a7" stroke-width="3"></path>
    <path d="${linePath("negativePct")}" fill="none" stroke="#d94045" stroke-width="3"></path>
    ${points("positivePct", "#00a7a7")}
    ${points("negativePct", "#d94045")}
    ${labels}
    <text x="${left + width - 130}" y="18" class="bar-label" fill="#00a7a7">Positive %</text>
    <text x="${left + width - 45}" y="18" class="bar-label" fill="#d94045">Negative %</text>
  `;
  if ($("sentimentTrendChartNote")) $("sentimentTrendChartNote").textContent = sentimentTrendInsight(trend);
}

function sentimentTrendRows(rows) {
  const groups = new Map();
  rows.forEach((row) => {
    const key = normalizeDateKey(row["Feedback Date"]);
    if (!key) return;
    if (!groups.has(key)) groups.set(key, { Label: key, total: 0, positive: 0, negative: 0 });
    const group = groups.get(key);
    group.total += 1;
    if (row.Sentiment === "Positive") group.positive += 1;
    if (row.Sentiment === "Negative") group.negative += 1;
  });
  return [...groups.values()]
    .sort((a, b) => new Date(a.Label) - new Date(b.Label))
    .slice(-10)
    .map((group) => ({
      ...group,
      positivePct: Number(((group.positive / group.total) * 100).toFixed(1)),
      negativePct: Number(((group.negative / group.total) * 100).toFixed(1)),
    }));
}

function normalizeDateKey(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 10);
}

function shortDateLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function sentimentTrendInsight(trend) {
  if (trend.length < 2) return "Not enough dated rows for a trend.";
  const first = trend[0];
  const last = trend[trend.length - 1];
  const negativeMove = Number((last.negativePct - first.negativePct).toFixed(1));
  const direction = negativeMove > 0 ? "up" : negativeMove < 0 ? "down" : "flat";
  return `Negative sentiment is ${direction} ${Math.abs(negativeMove)} points from ${shortDateLabel(first.Label)} to ${shortDateLabel(last.Label)}.`;
}

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString() : "";
}

function formatDuration(ms) {
  const totalSeconds = Math.max(0, Math.round(Number(ms || 0) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function handleUploadFile(file) {
  if (!file) return;
  inspectFile(file).catch((err) => {
    $("fileStatus").textContent = friendlyError(err.message);
  });
}

document.querySelectorAll("[data-tab-target]").forEach((button) => {
  button.addEventListener("click", () => switchTab(button.dataset.tabTarget));
});

$("dataFile").addEventListener("change", (event) => handleUploadFile(event.target.files[0]));

const dropZone = document.querySelector(".drop-zone");
if (dropZone) {
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("drag");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("drag");
    });
  });
  dropZone.addEventListener("drop", (event) => handleUploadFile(event.dataTransfer.files[0]));
}

$("sentimentFilter").addEventListener("change", (event) => {
  state.filters.sentiment = event.target.value;
  applyFilters();
  renderResults(state.last);
});

$("sentimentSearch").addEventListener("input", (event) => {
  state.filters.search = event.target.value;
  applyFilters();
  renderResults(state.last);
});

$("clearSentimentFilters").addEventListener("click", () => {
  state.filters = { sentiment: "", search: "" };
  $("sentimentFilter").value = "";
  $("sentimentSearch").value = "";
  applyFilters();
  renderResults(state.last);
});

function handleRowTableOpen(event) {
  const row = event.target.closest("[data-row-index]");
  if (row) openRowReview(Number(row.dataset.rowIndex));
}

$("dashboardRowsTable").addEventListener("dblclick", handleRowTableOpen);
$("rowsTable").addEventListener("dblclick", handleRowTableOpen);

$("rowModal").addEventListener("click", (event) => {
  if (event.target.matches("[data-review-prev]")) openRowReview(state.selectedRowIndex - 1);
  if (event.target.matches("[data-review-next]")) openRowReview(state.selectedRowIndex + 1);
  if (event.target.matches("[data-review-override]")) overrideCurrentRow();
});

document.querySelectorAll("[data-close-modal]").forEach((button) => {
  button.addEventListener("click", () => $(button.dataset.closeModal).classList.add("hidden"));
});

document.querySelectorAll("[data-cloud-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    state.cloudMode = button.dataset.cloudMode;
    document.querySelectorAll("[data-cloud-mode]").forEach((item) => item.classList.toggle("active", item === button));
    renderWordCloud();
  });
});

document.querySelectorAll("[data-export-pdf]").forEach((button) => {
  button.addEventListener("click", exportPdfEnhanced);
});

document.querySelectorAll("[data-export-csv]").forEach((button) => {
  button.addEventListener("click", exportCsv);
});

$("wordCloud").addEventListener("click", (event) => {
  const button = event.target.closest("[data-cloud-term]");
  if (button) showWordMatches(button.dataset.cloudTerm);
});

$("wordEvidenceTable").addEventListener("dblclick", (event) => {
  const row = event.target.closest("[data-cloud-term]");
  if (row) showWordMatches(row.dataset.cloudTerm);
});

$("analyzeBtn").addEventListener("click", () => analyze().catch((err) => {
  stopLoading();
  alert(friendlyError(err.message));
}));

loadDefaults();
