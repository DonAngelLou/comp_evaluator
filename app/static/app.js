const form = document.getElementById("evaluation-form");
const submitButton = document.getElementById("submit-button");
const statusBox = document.getElementById("status-box");
const emptyState = document.getElementById("empty-state");
const reportView = document.getElementById("report-view");

const metricCompany = document.getElementById("metric-company");
const metricVerdict = document.getElementById("metric-verdict");
const metricScore = document.getElementById("metric-score");
const metricConfidence = document.getElementById("metric-confidence");
const snapshotList = document.getElementById("snapshot-list");
const projectionList = document.getElementById("projection-list");
const activityList = document.getElementById("activity-list");
const riskList = document.getElementById("risk-list");
const reportHtml = document.getElementById("report-html");
const citationList = document.getElementById("citation-list");

function setStatus(label, message) {
  statusBox.innerHTML = `
    <span class="status-label">${escapeHtml(label)}</span>
    <p>${escapeHtml(message)}</p>
  `;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderList(items, mapper) {
  if (!items || items.length === 0) {
    return "<div class=\"activity-item\">No data available.</div>";
  }
  return items.map(mapper).join("");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const payload = {
    company_name: document.getElementById("company_name").value.trim(),
    website: document.getElementById("website").value.trim(),
  };

  submitButton.disabled = true;
  submitButton.textContent = "Generating...";
  setStatus("Running", "Fetching sources, checking relevance, and generating the report.");

  try {
    const response = await fetch("/api/v1/evaluations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Request failed.");
    }

    emptyState.classList.add("hidden");
    reportView.classList.remove("hidden");

    metricCompany.textContent = data.company_profile.canonical_name;
    metricVerdict.textContent = data.verdict.replaceAll("_", " ");
    metricScore.textContent = `${data.scores.overall}/100`;
    metricConfidence.textContent = `${Math.round(data.company_profile.identity_confidence * 100)}%`;

    snapshotList.innerHTML = [
      `Domain: ${escapeHtml(data.company_profile.domain)}`,
      `Ticker: ${escapeHtml(data.company_profile.ticker || "n/a")}`,
      `Public company: ${data.company_profile.public_company ? "yes" : "no"}`,
      `Revenue growth YoY: ${formatPercent(data.financial_snapshot.revenue_growth_yoy)}`,
      `Net income margin: ${formatPercent(data.financial_snapshot.net_income_margin)}`,
      `Accepted sources: ${escapeHtml(data.source_summary.accepted_sources)}`,
    ]
      .map((item) => `<li>${item}</li>`)
      .join("");

    projectionList.innerHTML = [
      `${escapeHtml(data.upside_projection.bull_case.name)}: ${data.upside_projection.bull_case.projected_return_pct}%`,
      `${escapeHtml(data.upside_projection.base_case.name)}: ${data.upside_projection.base_case.projected_return_pct}%`,
      `${escapeHtml(data.upside_projection.bear_case.name)}: ${data.upside_projection.bear_case.projected_return_pct}%`,
    ]
      .map((item) => `<li>${item}</li>`)
      .join("");

    activityList.innerHTML = renderList(data.recent_activity, (item) => `
      <div class="activity-item">
        <small>${escapeHtml(item.date || "undated")} • ${escapeHtml(item.category)}</small>
        <strong>${escapeHtml(item.title)}</strong>
        <div>${escapeHtml(item.summary)}</div>
      </div>
    `);

    riskList.innerHTML = data.risks.length
      ? data.risks.map((risk) => `<span class="pill">${escapeHtml(risk)}</span>`).join("")
      : "<span class=\"pill\">No major risks listed.</span>";

    reportHtml.innerHTML = data.report_html;

    citationList.innerHTML = renderList(data.citations, (citation) => `
      <div class="citation-item">
        <small>${escapeHtml(citation.source_type)} • ${escapeHtml(citation.domain)}</small>
        <strong>${escapeHtml(citation.title)}</strong>
        <div><a href="${escapeHtml(citation.url)}" target="_blank" rel="noreferrer">Open source</a></div>
      </div>
    `);

    setStatus("Complete", "The report has been generated and rendered below.");
  } catch (error) {
    setStatus("Error", error.message || "The evaluation request failed.");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Generate Report";
  }
});

function formatPercent(value) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return `${(value * 100).toFixed(1)}%`;
}
