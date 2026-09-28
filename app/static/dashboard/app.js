"use strict";

/* ============================== API helper ============================== */

async function api(path, params) {
  const url = new URL(path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    }
  }
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) {}
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

async function apiPost(path) {
  const res = await fetch(path, { method: "POST" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) {}
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s === null || s === undefined ? "" : String(s);
  return d.innerHTML;
}

function fmtPct(value) {
  // null = the market is genuinely unavailable for this match (e.g. no
  // corners/cards data for its competition — see docs/architecture.md's
  // "Corners and cards" section), not a zero — shown as "N/A", not "0%".
  return value === null || value === undefined ? "N/A" : `${value}%`;
}

function marketLinesTableHtml(markets) {
  // `markets` is a list of {line, prob_over, prob_under, model_used} — one
  // row per offered line (see ml.prediction.predict.GOALS_LINES/
  // HT_GOALS_LINES/CORNERS_LINES/CARDS_LINES). prob_over/prob_under null
  // means this competition has no data for the stat at all — shown as
  // "N/A" for every line, not hidden, so it's clear the market was
  // considered and found unavailable.
  //
  // The Model column has three states, not two: a null line had *nothing*
  // computed for it (no dedicated model AND no Poisson baseline — there's
  // no data to fit one on), so labelling it "Poisson only" off a bare
  // `!model_used` would claim a Poisson number that was never produced —
  // the same misleading-flag trap `corners_model_used` already had to be
  // fixed for on the API side.
  const modelLabel = m => {
    if (m.prob_over === null || m.prob_over === undefined) return "—";
    return m.model_used ? "ML+Poisson" : "Poisson only";
  };
  const rows = markets.map(m => `
    <tr>
      <td>${m.line}</td>
      <td class="num">${fmtPct(m.prob_over)}</td>
      <td class="num">${fmtPct(m.prob_under)}</td>
      <td class="num">${modelLabel(m)}</td>
    </tr>`).join("");
  return `<table class="data"><thead><tr><th>Line</th><th class="num">Over</th><th class="num">Under</th><th class="num">Model</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function loadingHtml(label) {
  return `<div class="loading-state"><span class="spinner"></span>${esc(label || "Loading…")}</div>`;
}

function emptyHtml(label) {
  return `<div class="empty-state">${esc(label)}</div>`;
}

function errorHtml(err) {
  return `<div class="error-state">${esc(err.message || String(err))}</div>`;
}

/* ============================== Theme toggle ============================= */

(function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("up-theme"); } catch (_) {}
  if (saved) document.documentElement.setAttribute("data-theme", saved);

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("up-theme", next); } catch (_) {}
  });
})();

/* ================================= Router ================================= */

const VIEWS = ["matches", "match-detail", "standings", "team", "monitoring"];

function showView(id) {
  for (const v of VIEWS) {
    document.getElementById(`view-${v}`).classList.toggle("active", v === id);
  }
  for (const btn of document.querySelectorAll("#nav-tabs button")) {
    const isMatchesGroup = id === "matches" || id === "match-detail";
    const active = btn.dataset.route === id || (btn.dataset.route === "matches" && isMatchesGroup);
    btn.toggleAttribute("aria-current", active);
    if (active) btn.setAttribute("aria-current", "page"); else btn.removeAttribute("aria-current");
  }
}

function route() {
  const hash = window.location.hash.slice(1) || "matches";
  const [name, arg] = hash.split("/");

  if (name === "match" && arg) {
    showView("match-detail");
    renderMatchDetail(Number(arg));
  } else if (name === "standings") {
    showView("standings");
    renderStandings();
  } else if (name === "team") {
    showView("team");
    renderTeamView(arg ? decodeURIComponent(arg) : null);
  } else if (name === "monitoring") {
    showView("monitoring");
    renderMonitoring();
  } else {
    showView("matches");
    renderMatches();
  }
}

window.addEventListener("hashchange", route);

for (const btn of document.querySelectorAll("#nav-tabs button")) {
  btn.addEventListener("click", () => {
    window.location.hash = `#${btn.dataset.route}`;
  });
}

document.getElementById("back-to-matches").addEventListener("click", () => {
  window.location.hash = "#matches";
});

/* ============================ Shared: filter data ========================== */

let competitionsCache = null;
async function getCompetitions() {
  if (!competitionsCache) competitionsCache = await api("/competitions");
  return competitionsCache;
}

async function populateCompetitionSelect(selectEl, seasonSelectEl) {
  const data = await getCompetitions();
  const current = selectEl.value;
  selectEl.innerHTML = '<option value="">All competitions</option>' +
    data.competitions.map(c => `<option value="${esc(c.competition)}">${esc(c.competition)} (${c.match_count})</option>`).join("");
  selectEl.value = current;

  if (seasonSelectEl) {
    const fill = () => {
      const comp = data.competitions.find(c => c.competition === selectEl.value);
      const seasons = comp ? comp.seasons : [...new Set(data.competitions.flatMap(c => c.seasons))].sort();
      seasonSelectEl.innerHTML = '<option value="">All seasons</option>' +
        seasons.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
    };
    fill();
    selectEl.addEventListener("change", fill);
  }
}

/* =============================== Matches view =============================== */

async function renderMatches() {
  const wrap = document.getElementById("matches-table-wrap");
  wrap.innerHTML = loadingHtml("Loading matches…");

  try {
    await populateCompetitionSelect(document.getElementById("f-competition"), document.getElementById("f-season"));
  } catch (e) { /* filters are best-effort */ }

  await loadMatchesTable();
}

document.getElementById("f-apply").addEventListener("click", loadMatchesTable);

async function loadMatchesTable() {
  const wrap = document.getElementById("matches-table-wrap");
  wrap.innerHTML = loadingHtml("Loading matches…");

  const params = {
    competition: document.getElementById("f-competition").value,
    season: document.getElementById("f-season").value,
    status: document.getElementById("f-status").value,
    team: document.getElementById("f-team").value.trim(),
    limit: 50,
  };

  try {
    const data = await api("/matches", params);
    if (data.matches.length === 0) {
      wrap.innerHTML = emptyHtml("No matches match these filters.");
      return;
    }
    const rows = data.matches.map(m => `
      <tr class="clickable" data-match-id="${m.match_id}">
        <td>${fmtDate(m.match_date)}</td>
        <td>${esc(m.competition)}</td>
        <td>${esc(m.home_team)} vs ${esc(m.away_team)}</td>
        <td class="num">${m.status === "completed" ? `${m.home_score}-${m.away_score}` : "—"}</td>
        <td>${m.status === "completed" ? `<span class="badge neutral">completed</span>` : `<span class="badge good">scheduled</span>`}</td>
        <td>${m.has_odds ? "yes" : "—"}</td>
      </tr>`).join("");

    wrap.innerHTML = `
      <div class="spaced" style="margin-bottom:8px"><span class="muted">${data.count} match(es)${data.count > data.matches.length ? `, showing first ${data.matches.length}` : ""}</span></div>
      <table class="data">
        <thead><tr><th>Date</th><th>Competition</th><th>Fixture</th><th class="num">Score</th><th>Status</th><th>Odds</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;

    wrap.querySelectorAll("tr[data-match-id]").forEach(tr => {
      tr.addEventListener("click", () => { window.location.hash = `#match/${tr.dataset.matchId}`; });
    });
  } catch (e) {
    wrap.innerHTML = errorHtml(e);
  }
}

/* ============================= Match detail view ============================= */

function confidenceClass(label) {
  return { "Low": "low", "Medium": "medium", "High": "high", "Very High": "very-high" }[label] || "low";
}

function resultBarHtml(home, draw, away) {
  return `
    <div class="result-bar">
      <div class="seg home" style="flex:${Math.max(home, 0.001)}">${home >= 8 ? home.toFixed(1) + "%" : ""}</div>
      <div class="seg draw" style="flex:${Math.max(draw, 0.001)}">${draw >= 8 ? draw.toFixed(1) + "%" : ""}</div>
      <div class="seg away" style="flex:${Math.max(away, 0.001)}">${away >= 8 ? away.toFixed(1) + "%" : ""}</div>
    </div>
    <div class="result-legend">
      <div class="item"><span class="swatch" style="background:var(--series-1)"></span>Home ${home.toFixed(1)}%</div>
      <div class="item"><span class="swatch" style="background:var(--text-muted)"></span>Draw ${draw.toFixed(1)}%</div>
      <div class="item"><span class="swatch" style="background:var(--series-8)"></span>Away ${away.toFixed(1)}%</div>
    </div>`;
}

function signedBarsHtml(explanation) {
  if (!explanation || explanation.length === 0) {
    return emptyHtml("No SHAP explanation available (no match-result model trained yet).");
  }
  const maxAbs = Math.max(...explanation.map(f => Math.abs(f.impact_percentage_points)), 1);
  const rows = explanation.map(f => {
    const pct = Math.min(100, (Math.abs(f.impact_percentage_points) / maxAbs) * 50);
    const cls = f.impact_percentage_points >= 0 ? "pos" : "neg";
    return `
      <div class="signed-bar-row">
        <div class="name" title="${esc(f.feature)}">${esc(f.feature)}</div>
        <div class="signed-bar-track">
          <div class="zero"></div>
          <div class="fill ${cls}" style="width:${pct}%"></div>
        </div>
        <div class="val">${f.impact_percentage_points >= 0 ? "+" : ""}${f.impact_percentage_points.toFixed(1)}</div>
      </div>`;
  }).join("");
  return `<div class="signed-bars">${rows}</div>`;
}

function renderBasketballDetail(prediction) {
  // Two-way bar: no draw segment, because basketball has no draws (see
  // ml/prediction/predict_basketball.py). Reusing resultBarHtml with a 0
  // draw would render a stray empty segment and imply a draw exists.
  const confClass = confidenceClass(prediction.confidence_label);
  return `
    <h1>${esc(prediction.home_team)} vs ${esc(prediction.away_team)}</h1>
    <p class="muted">${fmtDateTime(prediction.match_date)} · ${esc(prediction.competition)}${prediction.model_version ? ` · model ${esc(prediction.model_version)}` : ""}</p>

    <div class="grid cols-2">
      <div class="card">
        <h3>Winner</h3>
        <div class="result-bar">
          <div class="seg home" style="flex:${Math.max(prediction.home_win, 0.001)}">${prediction.home_win >= 8 ? prediction.home_win.toFixed(1) + "%" : ""}</div>
          <div class="seg away" style="flex:${Math.max(prediction.away_win, 0.001)}">${prediction.away_win >= 8 ? prediction.away_win.toFixed(1) + "%" : ""}</div>
        </div>
        <div class="result-legend">
          <div class="item"><span class="swatch" style="background:var(--series-1)"></span>Home ${prediction.home_win.toFixed(1)}%</div>
          <div class="item"><span class="swatch" style="background:var(--series-8)"></span>Away ${prediction.away_win.toFixed(1)}%</div>
        </div>
        <div class="row" style="margin-top:12px">
          <span class="confidence-pill ${confClass}">${esc(prediction.confidence_label)} confidence (${prediction.confidence}%)</span>
        </div>
      </div>
      <div class="card">
        <h3>Expected points</h3>
        <div class="grid cols-3">
          <div class="stat-tile"><div class="label">Home</div><div class="value">${prediction.expected_points_home}</div></div>
          <div class="stat-tile"><div class="label">Away</div><div class="value">${prediction.expected_points_away}</div></div>
          <div class="stat-tile"><div class="label">Total</div><div class="value">${prediction.expected_total_points}</div></div>
        </div>
        <p class="muted" style="margin-top:10px">
          ${prediction.winner_model_used ? "ML+Elo" : "Elo only"} · no draw market — basketball plays overtime until someone wins
        </p>
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Total points</h3>
        ${marketLinesTableHtml(prediction.total_points_markets)}
        ${prediction.total_points_markets.every(m => m.prob_over === null)
          ? `<p class="muted" style="margin-top:8px">Not available — no trained model for these lines yet (there is no Poisson fallback for basketball).</p>`
          : ""}
      </div>
    </div>
  `;
}

async function renderMatchDetail(matchId) {
  const el = document.getElementById("match-detail-content");
  el.innerHTML = loadingHtml("Loading prediction…");

  let prediction;
  try {
    prediction = await api(`/predict/${matchId}`);
  } catch (e) {
    el.innerHTML = errorHtml(e);
    return;
  }

  // Basketball returns a different response shape (no draw, no goal
  // markets) — see docs/api_reference.md. Rendering it through the football
  // template below would read `prediction.draw` and `top_scorelines` off an
  // object that has neither, so it gets its own renderer rather than a
  // football view full of "undefined".
  if (prediction.sport === "basketball") {
    el.innerHTML = renderBasketballDetail(prediction);
    return;
  }

  const confClass = confidenceClass(prediction.confidence_label);
  const scorelinesRows = prediction.top_scorelines.map(s =>
    `<tr><td>${esc(s.score)}</td><td class="num">${(s.probability * 100).toFixed(1)}%</td></tr>`).join("");

  el.innerHTML = `
    <h1>${esc(prediction.home_team)} vs ${esc(prediction.away_team)}</h1>
    <p class="muted">${fmtDateTime(prediction.match_date)}${prediction.model_version ? ` · model ${esc(prediction.model_version)}` : ""}</p>

    <div class="grid cols-2">
      <div class="card">
        <h3>Result probability</h3>
        ${resultBarHtml(prediction.home_win, prediction.draw, prediction.away_win)}
        <div class="row" style="margin-top:12px">
          <span class="confidence-pill ${confClass}">${esc(prediction.confidence_label)} confidence (${prediction.confidence}%)</span>
        </div>
      </div>
      <div class="card">
        <h3>Expected goals &amp; BTTS</h3>
        <div class="grid cols-3">
          <div class="stat-tile"><div class="label">Home xG</div><div class="value">${prediction.expected_goals_home}</div></div>
          <div class="stat-tile"><div class="label">Away xG</div><div class="value">${prediction.expected_goals_away}</div></div>
          <div class="stat-tile"><div class="label">BTTS Yes</div><div class="value small">${prediction.btts_yes}%</div></div>
          <div class="stat-tile"><div class="label">BTTS No</div><div class="value small">${prediction.btts_no}%</div></div>
        </div>
        <p class="muted" style="margin-top:10px;font-size:12px">
          Weights: ${Object.entries(prediction.model_weights_used).map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`).join(", ")}
          ${prediction.btts_model_used ? " · GBM BTTS active" : " · BTTS from Poisson only"}
        </p>
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Goals</h3>
        ${marketLinesTableHtml(prediction.goals_markets)}
      </div>
      <div class="card">
        <h3>Half-time goals</h3>
        ${marketLinesTableHtml(prediction.ht_goals_markets)}
        ${prediction.ht_goals_markets.every(m => m.prob_over === null)
          ? `<p class="muted" style="margin-top:10px;font-size:12px">Not available — this competition has no half-time score data (see docs/architecture.md).</p>`
          : ""}
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Corners</h3>
        ${marketLinesTableHtml(prediction.corners_markets)}
        ${prediction.corners_markets.every(m => m.prob_over === null)
          ? `<p class="muted" style="margin-top:10px;font-size:12px">Not available — this competition has no corners data (see docs/architecture.md).</p>`
          : ""}
      </div>
      <div class="card">
        <h3>Cards</h3>
        ${marketLinesTableHtml(prediction.cards_markets)}
        ${prediction.cards_markets.every(m => m.prob_over === null)
          ? `<p class="muted" style="margin-top:10px;font-size:12px">Not available — this competition has no cards data (see docs/architecture.md).</p>`
          : ""}
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Top scorelines</h3>
        <table class="data"><thead><tr><th>Score</th><th class="num">Probability</th></tr></thead><tbody>${scorelinesRows}</tbody></table>
      </div>
      <div class="card">
        <h3>Why (SHAP, top contributing features)</h3>
        ${signedBarsHtml(prediction.explanation)}
      </div>
    </div>

    <div class="card">
      <div class="spaced"><h3 style="margin:0">Value vs. bookmaker odds</h3></div>
      <div id="value-panel">${loadingHtml("Checking for odds…")}</div>
    </div>

    <div class="card">
      <div class="spaced"><h3 style="margin:0">Prediction timeline</h3></div>
      <div id="history-panel">${loadingHtml("Loading history…")}</div>
    </div>

    <div class="card">
      <div class="spaced">
        <h3 style="margin:0">AI Analyst</h3>
        <button class="primary" id="ask-analyst-btn">Ask the analyst</button>
      </div>
      <div id="analyst-panel" class="muted">Click "Ask the analyst" for a narrative grounded in the data above (needs ANTHROPIC_API_KEY configured on the server).</div>
    </div>
  `;

  document.getElementById("ask-analyst-btn").addEventListener("click", () => runAnalyst(matchId));

  loadValuePanel(matchId);
  loadHistoryPanel(matchId);
}

async function loadValuePanel(matchId) {
  const panel = document.getElementById("value-panel");
  try {
    const value = await api(`/value/${matchId}`);
    const rows = value.edges.map(e => `
      <tr>
        <td>${esc(e.outcome.replace("_", " "))}</td>
        <td class="num">${e.model_probability.toFixed(1)}%</td>
        <td class="num">${e.market_implied_probability.toFixed(1)}%</td>
        <td class="num"><strong style="color:${e.edge >= 0 ? "var(--success-text)" : "var(--status-critical)"}">${e.edge >= 0 ? "+" : ""}${e.edge.toFixed(1)}pp</strong></td>
      </tr>`).join("");
    panel.innerHTML = `
      <p class="muted" style="font-size:12px">Odds: home ${value.odds_home_win} · draw ${value.odds_draw} · away ${value.odds_away_win}</p>
      <table class="data"><thead><tr><th>Outcome</th><th class="num">Model</th><th class="num">Market</th><th class="num">Edge</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="muted" style="font-size:11px;margin-top:8px">${esc(value.disclaimer)}</p>`;
  } catch (e) {
    panel.innerHTML = emptyHtml(e.status === 404 ? "No bookmaker odds available for this match." : e.message);
  }
}

async function loadHistoryPanel(matchId) {
  const panel = document.getElementById("history-panel");
  try {
    const history = await api(`/history/${matchId}`);
    if (history.timeline.length === 0) {
      panel.innerHTML = emptyHtml("No prediction history recorded yet — call /predict again later to build a timeline.");
      return;
    }
    panel.innerHTML = lineChart(
      history.timeline.map(p => ({ x: new Date(p.created_at), y: p.home_win })),
      { yLabel: "Home win %", yMax: 100, color: "var(--series-1)" }
    );
  } catch (e) {
    panel.innerHTML = errorHtml(e);
  }
}

async function runAnalyst(matchId) {
  const panel = document.getElementById("analyst-panel");
  const btn = document.getElementById("ask-analyst-btn");
  btn.disabled = true;
  panel.innerHTML = loadingHtml("Asking the analyst (real LLM tool-calling call, a few seconds)…");
  try {
    const result = await apiPost(`/analyst/${matchId}`);
    const toolCalls = result.tool_calls.map(tc => `
      <div class="tool-call">
        <span class="tool-name">${esc(tc.tool)}</span>
        <span class="muted">(${esc(JSON.stringify(tc.input))})</span>
        <pre>${esc(JSON.stringify(tc.result, null, 2))}</pre>
      </div>`).join("");
    panel.innerHTML = `
      <div class="analyst-narrative">${esc(result.analysis)}</div>
      <p class="muted" style="font-size:12px">Model: ${esc(result.model)} · ${result.tool_calls.length} tool call(s)</p>
      <details><summary class="muted" style="cursor:pointer;font-size:12px">Show tool call trace</summary>${toolCalls}</details>`;
  } catch (e) {
    panel.innerHTML = e.status === 503
      ? emptyHtml(e.message)
      : errorHtml(e);
  } finally {
    btn.disabled = false;
  }
}

/* =============================== Standings view =============================== */

async function renderStandings() {
  const compSel = document.getElementById("s-competition");
  const seasonSel = document.getElementById("s-season");
  const wrap = document.getElementById("standings-table-wrap");

  try {
    await populateCompetitionSelect(compSel, seasonSel);
  } catch (e) {
    wrap.innerHTML = errorHtml(e);
    return;
  }

  const load = async () => {
    if (!compSel.value) { wrap.innerHTML = emptyHtml("Pick a competition to see its table."); return; }
    wrap.innerHTML = loadingHtml("Loading standings…");
    try {
      const data = await api(`/standings/${encodeURIComponent(compSel.value)}`, { season: seasonSel.value });
      const rows = data.table.map((r, i) => `
        <tr>
          <td class="num">${i + 1}</td>
          <td>${esc(r.team)}</td>
          <td class="num">${r.played}</td>
          <td class="num">${r.won}</td>
          <td class="num">${r.drawn}</td>
          <td class="num">${r.lost}</td>
          <td class="num">${r.goals_for}</td>
          <td class="num">${r.goals_against}</td>
          <td class="num">${r.goal_difference >= 0 ? "+" : ""}${r.goal_difference}</td>
          <td class="num"><strong>${r.points}</strong></td>
        </tr>`).join("");
      wrap.innerHTML = `
        <p class="muted">${esc(data.competition)} — ${esc(data.season || "")}</p>
        <table class="data">
          <thead><tr><th>#</th><th>Team</th><th class="num">P</th><th class="num">W</th><th class="num">D</th><th class="num">L</th><th class="num">GF</th><th class="num">GA</th><th class="num">GD</th><th class="num">Pts</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>`;
    } catch (e) {
      wrap.innerHTML = e.status === 404 ? emptyHtml("No completed matches for that competition/season.") : errorHtml(e);
    }
  };

  compSel.onchange = load;
  seasonSel.onchange = load;
  load();
}

/* ================================= Team view ================================= */

document.getElementById("t-search").addEventListener("click", () => {
  const name = document.getElementById("t-name").value.trim();
  if (name) window.location.hash = `#team/${encodeURIComponent(name)}`;
});
document.getElementById("t-name").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("t-search").click();
});

async function renderTeamView(name) {
  const el = document.getElementById("team-content");
  if (!name) { el.innerHTML = emptyHtml("Search for a team by name."); return; }
  document.getElementById("t-name").value = name;
  el.innerHTML = loadingHtml(`Loading ${name}…`);

  try {
    const [team, elo] = await Promise.all([api(`/team/${encodeURIComponent(name)}`), api(`/elo/${encodeURIComponent(name)}`)]);

    const recentRows = team.recent_matches.map(m => `
      <tr><td>${fmtDate(m.match_date)}</td><td>${esc(m.home_team)} ${m.home_score ?? "-"} - ${m.away_score ?? "-"} ${esc(m.away_team)}</td></tr>
    `).join("");

    const eloPoints = elo.history.map(p => ({ x: new Date(p.match_date), y: p.rating_after }));

    el.innerHTML = `
      <h1>${esc(team.team.name)}</h1>
      <p class="muted">${esc(team.team.league || "")}</p>
      <div class="grid cols-3">
        <div class="stat-tile"><div class="label">Current Elo</div><div class="value">${team.team.elo_rating.toFixed(0)}</div></div>
        <div class="stat-tile"><div class="label">Form (last 5)</div><div class="value small">${team.form_last5.wins}W ${team.form_last5.draws}D ${team.form_last5.losses}L</div></div>
        <div class="stat-tile"><div class="label">Form (last 10)</div><div class="value small">${team.form_last10.wins}W ${team.form_last10.draws}D ${team.form_last10.losses}L</div></div>
      </div>
      <div class="card">
        <h3>Elo history (${eloPoints.length} matches)</h3>
        ${eloPoints.length > 1 ? lineChart(eloPoints, { yLabel: "Elo", color: "var(--series-1)" }) : emptyHtml("Not enough history yet.")}
      </div>
      <div class="grid cols-2">
        <div class="card">
          <h3>Recent matches</h3>
          ${recentRows ? `<table class="data"><tbody>${recentRows}</tbody></table>` : emptyHtml("No completed matches.")}
        </div>
        <div class="card">
          <h3>Injuries</h3>
          <div id="team-injuries">${loadingHtml("Checking injuries…")}</div>
        </div>
      </div>
    `;

    loadTeamInjuries(name);
  } catch (e) {
    el.innerHTML = e.status === 404 ? emptyHtml(`No team found matching "${name}".`) : errorHtml(e);
  }
}

async function loadTeamInjuries(name) {
  const el = document.getElementById("team-injuries");
  try {
    const data = await api(`/injuries/${encodeURIComponent(name)}`);
    if (!data.available) {
      el.innerHTML = emptyHtml(data.message);
      return;
    }
    if (data.injuries.length === 0) {
      el.innerHTML = emptyHtml("Synced — no current injuries reported.");
      return;
    }
    const rows = data.injuries.map(i => `<tr><td>${esc(i.player_name)}</td><td>${esc(i.reason || i.injury_type || "—")}</td></tr>`).join("");
    el.innerHTML = `<table class="data"><tbody>${rows}</tbody></table><p class="muted" style="font-size:11px;margin-top:6px">Synced ${fmtDateTime(data.synced_at)}</p>`;
  } catch (e) {
    el.innerHTML = errorHtml(e);
  }
}

/* ============================= Model monitoring view ============================= */

function barChart(items, opts) {
  // items: [{label, value}]; opts: {color, height}
  const width = 560, height = opts.height || 160, padL = 8, padB = 28, padT = 8, padR = 8;
  const plotW = width - padL - padR, plotH = height - padT - padB;
  const maxV = Math.max(...items.map(d => d.value), 1);
  const bw = plotW / items.length;
  const bars = items.map((d, i) => {
    const h = (d.value / maxV) * plotH;
    const x = padL + i * bw + bw * 0.15;
    const w = bw * 0.7;
    const y = padT + plotH - h;
    return `<rect x="${x}" y="${y}" width="${w}" height="${Math.max(h, 1)}" rx="3" fill="${opts.color}"><title>${esc(d.label)}: ${d.value}</title></rect>
            <text x="${x + w / 2}" y="${height - 8}" text-anchor="middle">${esc(d.label)}</text>`;
  }).join("");
  return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" width="100%" style="max-width:${width}px">
    <line class="axis-line" x1="${padL}" y1="${padT + plotH}" x2="${padL + plotW}" y2="${padT + plotH}"></line>
    ${bars}
  </svg>`;
}

function scatterChart(points, opts) {
  // points: [{x, y, r?}], diagonal reference line, both axes 0-100
  const width = 320, height = 320, pad = 34;
  const plot = width - pad * 2;
  const sx = v => pad + (v / 100) * plot;
  const sy = v => pad + plot - (v / 100) * plot;

  const grid = [0, 25, 50, 75, 100].map(v => `
    <line class="gridline" x1="${sx(v)}" y1="${pad}" x2="${sx(v)}" y2="${pad + plot}"></line>
    <line class="gridline" x1="${pad}" y1="${sy(v)}" x2="${pad + plot}" y2="${sy(v)}"></line>
    <text x="${sx(v)}" y="${pad + plot + 14}" text-anchor="middle">${v}</text>
    <text x="${pad - 6}" y="${sy(v) + 3}" text-anchor="end">${v}</text>
  `).join("");

  const dots = points.map(p => `
    <circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="${Math.max(4, Math.min(14, p.r || 5))}" fill="${opts.color}" fill-opacity="0.85">
      <title>Predicted ${p.x.toFixed(1)}% → actual ${p.y.toFixed(1)}% (n=${p.n || "?"})</title>
    </circle>`).join("");

  return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" width="100%" style="max-width:${width}px">
    ${grid}
    <line class="ref-line" x1="${sx(0)}" y1="${sy(0)}" x2="${sx(100)}" y2="${sy(100)}"></line>
    <line class="axis-line" x1="${pad}" y1="${pad + plot}" x2="${pad + plot}" y2="${pad + plot}"></line>
    <line class="axis-line" x1="${pad}" y1="${pad}" x2="${pad}" y2="${pad + plot}"></line>
    ${dots}
    <text x="${pad + plot / 2}" y="${height - 2}" text-anchor="middle">Predicted probability (%)</text>
    <text x="10" y="${pad + plot / 2}" text-anchor="middle" transform="rotate(-90 10 ${pad + plot / 2})">Actual accuracy (%)</text>
  </svg>`;
}

function lineChart(points, opts) {
  if (points.length === 0) return emptyHtml("No data.");
  const width = 560, height = 180, pad = 30;
  const plotW = width - pad * 2, plotH = height - pad * 2;
  const xs = points.map(p => p.x.getTime());
  const ys = points.map(p => p.y);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = opts.yMin !== undefined ? opts.yMin : Math.min(...ys) - 5;
  const yMax = opts.yMax !== undefined ? opts.yMax : Math.max(...ys) + 5;
  const sx = t => pad + (xMax === xMin ? plotW / 2 : ((t - xMin) / (xMax - xMin)) * plotW);
  const sy = v => pad + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH;

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x.getTime())},${sy(p.y)}`).join(" ");
  const dots = points.map(p => `<circle cx="${sx(p.x.getTime())}" cy="${sy(p.y)}" r="3.5" fill="${opts.color}"><title>${p.x.toLocaleString()}: ${p.y.toFixed(1)}</title></circle>`).join("");

  return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" width="100%" style="max-width:${width}px">
    <line class="axis-line" x1="${pad}" y1="${pad + plotH}" x2="${pad + plotW}" y2="${pad + plotH}"></line>
    <line class="axis-line" x1="${pad}" y1="${pad}" x2="${pad}" y2="${pad + plotH}"></line>
    <path d="${path}" fill="none" stroke="${opts.color}" stroke-width="2"></path>
    ${dots}
    <text x="${pad - 6}" y="${pad + 4}" text-anchor="end">${opts.yMax !== undefined ? opts.yMax : Math.round(yMax)}</text>
    <text x="${pad - 6}" y="${pad + plotH}" text-anchor="end">${opts.yMin !== undefined ? opts.yMin : Math.round(yMin)}</text>
  </svg>`;
}

function driftBadge(detected, hasHistory) {
  if (!hasHistory) return `<span class="badge neutral">not enough history</span>`;
  return detected ? `<span class="badge warning">drift detected</span>` : `<span class="badge good">no drift</span>`;
}

async function renderMonitoring() {
  const el = document.getElementById("monitoring-content");
  el.innerHTML = loadingHtml("Loading model performance…");

  // The ROI backtest recomputes a full ensemble prediction for every
  // held-out match with odds — live-measured at ~2 minutes uncached. It's
  // deliberately NOT fetched here alongside the fast panels (that would
  // block the whole page on it); it loads on demand from its own button
  // below, with the server-side cache (routes_roi.py) making repeat visits
  // fast once someone's run it once.
  const modelNames = [
    "xgboost_match_result",
    "gbm_btts",
    // One model per offered line — see ml.prediction.predict.GOALS_LINES/
    // HT_GOALS_LINES/CORNERS_LINES/CARDS_LINES, and each
    // ml.training.train_*'s model_name_for_line for the naming convention.
    "lightgbm_over_under_1_5",
    "lightgbm_over_under_2_5",
    "lightgbm_over_under_ht_goals_0_5",
    "lightgbm_over_under_corners_7_5",
    "lightgbm_over_under_corners_8_5",
    "lightgbm_over_under_corners_9_5",
    "gbm_over_under_cards_2_5",
    "gbm_over_under_cards_3_5",
    "gbm_over_under_cards_4_5",
    // Basketball — a separate sport with its own models, not more football
    // lines. See ml/prediction/predict_basketball.py's TOTAL_POINTS_LINES.
    "lightgbm_basketball_winner",
    "lightgbm_basketball_total_215_5",
    "lightgbm_basketball_total_225_5",
    "lightgbm_basketball_total_235_5",
    // Tennis — see ml/prediction/predict_tennis.py's TOTAL_GAMES_LINES.
    "lightgbm_tennis_winner",
    "lightgbm_tennis_total_games_19_5",
    "lightgbm_tennis_total_games_21_5",
    "lightgbm_tennis_total_games_23_5",
  ];
  try {
    const [performances, monitoring] = await Promise.all([
      Promise.all(modelNames.map(m => api("/model/performance", { model_name: m }).catch(() => null))),
      api("/model/monitoring"),
    ]);

    const perfCards = performances.map((p, i) => {
      if (!p || !p.active_version) return `<div class="stat-tile"><div class="label">${modelNames[i]}</div><div class="value small muted">not trained</div></div>`;
      const m = p.active_version.metrics;
      return `<div class="stat-tile">
        <div class="label">${esc(p.model_name)}</div>
        <div class="value small">${(m.accuracy * 100).toFixed(1)}% acc</div>
        <div class="delta muted">log-loss ${m.log_loss} · v${esc(p.active_version.version.slice(0, 8))}</div>
      </div>`;
    }).join("");

    const cal = monitoring.calibration;
    const scatterPoints = cal.buckets.map(b => ({ x: b.mean_predicted_probability, y: b.actual_accuracy, n: b.count, r: 4 + Math.sqrt(b.count) }));
    const bucketBars = cal.buckets.map(b => ({ label: `${b.bucket_low}-${b.bucket_high}`, value: b.count }));

    const featureShiftRows = monitoring.feature_drift.shifted_features.map(f =>
      `<tr><td>${esc(f.feature)}</td><td class="num">${f.previous_mean}</td><td class="num">${f.latest_mean}</td><td class="num">${f.shift}σ</td></tr>`).join("");

    el.innerHTML = `
      <div class="card">
        <h3>Active model versions</h3>
        <div class="grid cols-3">${perfCards}</div>
      </div>

      <div class="grid cols-2">
        <div class="card">
          <h3>Calibration (${cal.num_predictions} evaluated predictions, Brier ${cal.brier_score})</h3>
          ${cal.buckets.length ? scatterChart(scatterPoints, { color: "var(--series-1)" }) : emptyHtml("Not enough evaluated predictions yet.")}
        </div>
        <div class="card">
          <h3>Prediction volume by confidence bucket</h3>
          ${cal.buckets.length ? barChart(bucketBars, { color: "var(--series-1)" }) : emptyHtml("Not enough evaluated predictions yet.")}
        </div>
      </div>

      <div class="grid cols-2">
        <div class="card">
          <h3>Metric drift ${driftBadge(monitoring.drift.drift_detected, monitoring.drift.has_enough_history)}</h3>
          <p class="secondary" style="font-size:13px">${monitoring.drift.reasons.map(esc).join("<br>")}</p>
        </div>
        <div class="card">
          <h3>Feature drift ${driftBadge(monitoring.feature_drift.drift_detected, monitoring.feature_drift.has_enough_history)}</h3>
          ${featureShiftRows
            ? `<table class="data"><thead><tr><th>Feature</th><th class="num">Prev mean</th><th class="num">Latest mean</th><th class="num">Shift</th></tr></thead><tbody>${featureShiftRows}</tbody></table>`
            : `<p class="secondary" style="font-size:13px">${monitoring.feature_drift.reasons.map(esc).join("<br>")}</p>`}
        </div>
      </div>

      <div class="card">
        <div class="spaced">
          <h3 style="margin:0">ROI backtest (held-out test matches only)</h3>
          <button class="primary" id="run-roi-btn">Run ROI backtest</button>
        </div>
        <p class="muted" style="font-size:12px;margin:4px 0 0">Recomputes a real prediction for every held-out match — can take up to a couple of minutes the first time; cached for an hour after that.</p>
        <div id="roi-panel" style="margin-top:10px"></div>
      </div>
    `;

    document.getElementById("run-roi-btn").addEventListener("click", loadRoiPanel);
  } catch (e) {
    el.innerHTML = errorHtml(e);
  }
}

async function loadRoiPanel() {
  const panel = document.getElementById("roi-panel");
  const btn = document.getElementById("run-roi-btn");
  btn.disabled = true;
  panel.innerHTML = loadingHtml("Running backtest (this can take a couple of minutes)…");
  try {
    const roi = await api("/model/roi-backtest");
    panel.innerHTML = `
      <div class="grid cols-4">
        <div class="stat-tile"><div class="label">Bets placed</div><div class="value small">${roi.num_bets}</div></div>
        <div class="stat-tile"><div class="label">Hit rate</div><div class="value small">${roi.hit_rate_percent}%</div></div>
        <div class="stat-tile"><div class="label">ROI</div><div class="value small" style="color:${roi.roi_percent >= 0 ? "var(--success-text)" : "var(--status-critical)"}">${roi.roi_percent >= 0 ? "+" : ""}${roi.roi_percent}%</div></div>
        <div class="stat-tile"><div class="label">Profit</div><div class="value small">${roi.profit >= 0 ? "+" : ""}${roi.profit}</div></div>
      </div>
      <p class="muted" style="font-size:11px;margin-top:8px">${esc(roi.disclaimer)} (edge threshold ${roi.edge_threshold}pp, stake ${roi.stake_per_bet}/bet, ${roi.num_matches_considered} held-out matches considered)</p>`;
  } catch (e) {
    panel.innerHTML = errorHtml(e);
  } finally {
    btn.disabled = false;
  }
}

/* =================================== Boot =================================== */

route();
