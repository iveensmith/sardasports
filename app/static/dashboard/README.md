# Dashboard

A plain HTML/CSS/vanilla-JS single-page dashboard on top of the API — no
build step, no Node.js, no new dependency. Served by FastAPI itself as
static files (`app/main.py` mounts this directory at `/dashboard`).

```
dashboard/
├── index.html   # shell: top nav + one <section> per view
├── style.css    # design tokens (validated palette) + component styles
└── app.js       # hash router, fetch() calls to the JSON API, chart rendering
```

## Views

| Route | What it shows |
|---|---|
| `#matches` | Filterable/browsable match list (competition, season, status, team) |
| `#match/{id}` | Full prediction (probabilities, scorelines, O/U, BTTS, SHAP explanation), value vs. bookmaker odds, prediction timeline, and an "Ask the analyst" button that calls the real AI agent |
| `#standings/{competition}` | Live league table |
| `#team/{name}` | Elo history chart, form, recent matches, injuries |
| `#monitoring` | Model performance, calibration scatter + volume chart, metric/feature drift, ROI backtest (opt-in button, not auto-loaded — see below) |

## The ROI backtest is opt-in, not auto-loaded

Live-measured at ~2 minutes uncached (it recomputes a full ensemble
prediction, including a from-scratch Poisson refit, for every held-out
match) — fetching it alongside the fast panels would block the whole
Monitoring page. It's a button instead, with its own loading state; the
server caches the result for an hour (`app/api/routes_roi.py`) so repeat
visits after the first run are instant. Found this by testing the built
dashboard against the real backend, not by guessing at it upfront.

## Charts

Built as plain inline SVG (no charting library), following the categorical/
sequential/diverging color roles and mark specs from the `dataviz` skill —
see `style.css`'s custom properties for the validated palette this project
draws from. Native `<title>` elements give browser tooltips on hover.

## Running it

```bash
uv run uvicorn app.main:app --reload
```

Visit `http://localhost:8000/dashboard`. No separate process, no `npm
install` — the same command that runs the API serves this.
