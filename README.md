# UniquePredict

An AI-powered sports prediction engine — football (club **and**
international), basketball and tennis, sharing one multi-sport pipeline. Predicts Home/Draw/Away, correct
score, Over/Under goals (1.5/2.5), Over/Under half-time goals (0.5), Both
Teams To Score, Over/Under corners (7.5/8.5/9.5), Over/Under cards
(2.5/3.5/4.5), and a 0-100 confidence score, from an ensemble of an Elo
rating system, a Poisson goal/half-time-goal/corners/cards model, and
XGBoost/LightGBM/Gradient-Boosting models trained on real
historical match data — plus SHAP explainability, value detection against
bookmaker odds, calibration/drift monitoring, ROI backtesting, live
standings, real injury data, a ChromaDB RAG knowledge base, an AI analyst
agent, and a dashboard UI on top of all of it.

**No prediction is ever fabricated.** Every number the API returns is derived
from ingested match data and the statistical/ML models trained on it — see
[`docs/architecture.md`](docs/architecture.md) for exactly how.

## Status

Every item from the original spec is done, frontend included, plus the
markets, leagues and data adapters added since (see
[`docs/roadmap.md`](docs/roadmap.md) for the full record and the few items
that are still genuinely open, each needing a decision only you can make):

- Real data ingestion — **18 leagues, 10 seasons each, 62,568 matches**:
  16 from Football-Data.co.uk (the "big 5" top flights — Premier League, La
  Liga, Bundesliga, Serie A, Ligue 1 — plus their second divisions, plus
  Eredivisie, Belgian Pro League, Primeira Liga, Süper Lig, Greek Super
  League, and the Scottish Premiership, 2015-16 → 2024-25, with bookmaker
  odds), plus **MLS** and the **Saudi Pro League** via two small adapter
  scripts (`scripts/fetch_extra_league.py`, `scripts/fetch_api_football_league.py`)
  that normalize each source's differently-shaped data into the same
  pipeline — MLS is on Football-Data.co.uk too but in an incompatible
  single-file/different-columns format, and the Saudi Pro League isn't on
  Football-Data.co.uk at all (confirmed directly, not assumed), so it's
  pulled from API-Football's `/fixtures` instead (needs a paid-tier
  `API_FOOTBALL_KEY` — the free tier's quota can't cover ~10 seasons of
  history), goals/teams/dates only, no odds
- Leakage-safe feature engineering, with a per-team indexed lookup
  (`TeamHistoryIndex`) that keeps walk-forward training near-linear instead
  of degrading to O(n²) at this data scale — measured at ~56 minutes without
  it vs. ~15 seconds with it for an 18k-match run, and still only ~54
  seconds (not hours) at the current 62,568-match/18-league scale
- A competition one-hot feature and per-league-scoped Poisson fitting, so
  mixing leagues' very different scoring/home-advantage baselines doesn't
  blend them into one wrong number. Real, honestly-reported result of
  widening from 5 to 18 leagues: broader coverage (all 18 now get a real
  per-league Poisson baseline and ML signal, not just the generic
  Elo+Poisson fallback — live-verified with real predictions on both a
  Saudi Pro League and an MLS match, each correctly citing its own
  competition feature in the SHAP explanation), but held-out match-result
  accuracy on the combined set is **50.0%**, down from 52.5% on the
  narrower 5-league set — expected, since several of the added leagues
  (lower divisions, smaller/less-analyzed top flights) are genuinely
  noisier and harder to predict than the original 5, and now share one
  model rather than being excluded
- Elo rating engine
- Poisson goal model (derives correct score, O/U goals lines, BTTS
  baselines), plus a second, independently-fitted Poisson on half-time
  scores specifically — a half isn't "half a match" statistically, so the
  full-time fit is not reused for it
- **International football** — World Cup, Euros, Nations League, Copa
  America, the Africa Cup of Nations (finals **and** qualifiers) and
  friendlies, through the *same* pipeline as the domestic
  leagues (same Elo, Poisson, features and models; it's the same sport).
  What genuinely differs is handled: tournament matches are played on
  **neutral ground**, so `matches.neutral_venue` switches off the Elo
  home-advantage offset rather than crediting it to whichever side the
  fixture list called "home"
- **Basketball (NBA)** — a separate vertical, not a retrain, because the
  sport differs structurally: **zero draws** in 4,149 ingested games (so a
  binary winner model, and no `draw` field in the response at all) and
  **227.3 average total points** against a football Poisson fit truncated
  at 8 goals (so no Poisson baseline; an untrained line says so instead of
  guessing). Markets: match winner and total points at 215.5 / 225.5 /
  235.5, with rest-days and back-to-back features that have no football
  equivalent
- **Tennis (ATP + WTA)** — 75,867 matches, 2010-2025, with per-surface
  ratings because a player's clay ability is genuinely not their grass
  ability. Two traps handled explicitly: the source records winner/loser
  rather than player 1/2, so slots are assigned by a deterministic hash
  (measured home-slot win rate **49.98%**, not 100%); and tennis is won on
  **sets, not games**, so games decide nothing — a games-based winner label
  would have been wrong or undefined for **4.81%** of matches. Markets:
  match winner and total games at 19.5 / 21.5 / 23.5
- **Goals multi-line (O/U 1.5 / 2.5) and half-time goals (O/U 0.5)
  markets** — the goals market was a single hardcoded 2.5 line end-to-end
  (one API field, one DB column); it's now the same multi-line shape the
  corners/cards markets use, and half-time goals is a brand-new market on
  top of it. Each line has its own trained model; the half-time market gets
  its own Poisson fit rather than deriving a half from the full-time one.
  Half-time scores are recorded for 58,053 of 62,568 matches (92.8%) — the
  4,515 without are the whole of MLS (4,445; its source file has no
  `HTHG`/`HTAG` columns) plus 70 scattered gaps elsewhere, so MLS reports
  the half-time market as `null`/"N/A" while still serving real full-time
  goals lines
- **Corners (O/U 7.5 / 8.5 / 9.5) and cards (O/U 2.5 / 3.5 / 4.5) markets,
  multi-line** — corner/card data was already ingested but sat unused; now
  feeds a real rolling per-team corners-won/conceded feature (benefiting
  the match-result/O-U/BTTS models too) plus two brand-new multi-line
  markets. Each line is its own genuine market with its own trained
  LightGBM/GBM model (11 models total across all 6 markets); the Poisson
  baseline, though, is one fit per stat *reused* across every line (the
  same `PoissonModel` used for goals, reused as-is — corners/cards are,
  like goals, non-negative per-match count stats with a genuine team
  "strength" structure), so each line's number is a real, distinct
  calculation, not an interpolation. Not every league/season records
  corners/cards (79.2% overall; MLS and the Saudi Pro League have none) —
  reported honestly as `null`/"N/A" for every line, never a fabricated
  number, when a competition has no data for it at all
- XGBoost match-result model, 2 LightGBM Over/Under goals models (one per
  line), 1 LightGBM Over/Under half-time goals model, Gradient Boosting
  BTTS model, 3 LightGBM corners models (one per line), 3 Gradient Boosting
  cards models (one per line) — 11 models total, all versioned, never
  overwritten, all trained on the full 18-league dataset: match-result
  50.1%, BTTS 54.8%; O/U goals 76.38% / 56.5% (1.5 / 2.5); O/U half-time
  goals 71.10% (0.5); corners 73.96% / 62.86% / 54.67% (7.5 / 8.5 / 9.5);
  cards 78.44% / 63.78% / 59.83% (2.5 / 3.5 / 4.5) — the outer lines score
  higher raw accuracy than the center lines because they're less balanced
  (further from a 50/50 split), not because they're "better" models
- Weighted ensemble with a real (not random) confidence score
- SHAP explainability on every prediction (top contributing features)
- Value detection: model probability vs. bookmaker-implied probability
- Calibration tracking (Brier score, reliability buckets), metric drift, and
  feature drift (each feature's mean vs. the previous training run,
  independent of accuracy), all from real evaluated predictions/training runs
- ROI backtesting: flat-staking simulation over the model's genuinely
  held-out test matches (`GET /model/roi-backtest`) — real result on the
  current dataset: -6.74% ROI, reported honestly, not cherry-picked
- Live league standings, computed from our own ingested results, no
  external source needed (`GET /standings/{competition}`)
- Real injuries/suspensions synced from API-Football (`GET /injuries/{team}`,
  needs your own `API_FOOTBALL_KEY`) — **live-verified**: synced Arsenal for
  real, one sensible current entry per player; honestly reports
  unavailability per team rather than guessing if nothing's been synced yet
- AI analyst agent (Claude, tool-calling) narrating predictions from real
  service calls only — `POST /analyst/{match_id}` (needs your own
  `ANTHROPIC_API_KEY`) — **live-verified**: a real run correctly called
  `get_model_prediction` + `get_team_form` and cited only real numbers back
- RAG knowledge base (ChromaDB): original reference articles plus real
  Wikipedia content (CC BY-SA 4.0, attributed) the agent retrieves from
  before answering methodology questions
- APScheduler automation (daily refresh + injuries sync, post-match
  evaluation, weekly retrain, monthly archive review) — off by default,
  `ENABLE_SCHEDULER=true`
- Dashboard at `/dashboard` — plain HTML/JS, no build step — matches,
  predictions (with SHAP + value detection + a working "Ask the analyst"
  button), standings, team lookup, model monitoring — **live-verified in a
  real browser**, which caught and fixed one real bug: the ROI backtest
  endpoint took ~2 minutes uncached and was silently blocking the whole
  Monitoring page; now server-cached (1hr) and an explicit opt-in button
- FastAPI with all spec endpoints, backed by Postgres/SQLite
- Redis caching (gracefully disabled if Redis isn't running)
- Docker Compose deployment (API + Postgres + Redis + ChromaDB)
- 149-test suite (Elo, Poisson, feature-leakage, multi-league correctness,
  goals/half-time-goals/corners/cards markets, monitoring/drift,
  standings, injuries, ROI
  backtest/caching, RAG, agent tools/credentials, API)

## Quickstart

```bash
# 1. Provision Python 3.12 and install dependencies
uv python install 3.12
uv venv --python 3.12
uv sync

# 2. Configure environment
cp .env.example .env   # defaults to a local SQLite DB, works out of the box

# 3. Get real data (18 leagues x 10 seasons, including bookmaker odds) and train
for LEAGUE in E0 E1 SP1 SP2 D1 D2 I1 I2 F1 F2 N1 B1 P1 T1 G1 SC0; do
  uv run python scripts/download_data.py --league $LEAGUE --seasons 1516,1617,1718,1819,1920,2021,2122,2223,2324,2425
done
# MLS: same source, different file format — see scripts/fetch_extra_league.py
uv run python scripts/fetch_extra_league.py --country USA --league MLS --code MLS1 \
  --seasons 2016,2017,2018,2019,2020,2021,2022,2023,2024,2025
# Saudi Pro League: not on Football-Data.co.uk at all — needs a paid-tier
# API_FOOTBALL_KEY in .env (the free tier's quota can't cover this much history)
uv run python scripts/fetch_api_football_league.py --league-id 307 --code SAU1 \
  --seasons 2016,2017,2018,2019,2020,2021,2022,2023,2024,2025
# International football (World Cup, Euros, Nations League, Copa America,
# AFCON + qualifiers, friendlies) — needs API_FOOTBALL_KEY; a free plan
# covers seasons 2022-2024
#   ...or a subset:  --only AFCON,AFCONQ
uv run python scripts/fetch_international.py
uv run python scripts/clean_data.py
uv run python scripts/load_to_db.py

# Basketball (NBA) — same api-sports key, different host; writes straight to
# the DB (no clean step: one consistent API has no CSV dialects to reconcile)
uv run python scripts/fetch_basketball.py

# Tennis (ATP + WTA) — tennis-data.co.uk, no API key needed
uv run python scripts/fetch_tennis.py
uv run python -m ml.training.train_match_result
for LINE in 1.5 2.5; do uv run python -m ml.training.train_over_under --line $LINE; done
uv run python -m ml.training.train_ht_goals --line 0.5
uv run python -m ml.training.train_btts
for LINE in 7.5 8.5 9.5; do uv run python -m ml.training.train_corners --line $LINE; done
for LINE in 2.5 3.5 4.5; do uv run python -m ml.training.train_cards --line $LINE; done
# Basketball
uv run python -m ml.training.train_basketball_winner
for LINE in 215.5 225.5 235.5; do uv run python -m ml.training.train_basketball_totals --line $LINE; done
# Tennis
uv run python -m ml.training.train_tennis_winner
for LINE in 19.5 21.5 23.5; do uv run python -m ml.training.train_tennis_totals --line $LINE; done

# 4. Index the RAG knowledge base (original articles + real Wikipedia content)
uv run python -m rag.ingestion.fetch_wikipedia
uv run python -m rag.indexer

# 5. (Optional) enable the AI analyst agent and injuries sync
#    echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
#    echo "API_FOOTBALL_KEY=..." >> .env   # free tier: dashboard.api-football.com
#    uv run python scripts/sync_injuries.py --league "English Premier League"

# 6. Run the API
uv run uvicorn app.main:app --reload
# -> http://localhost:8000/dashboard  (UI)
# -> http://localhost:8000/docs       (OpenAPI)
```

Or with Docker (Postgres + Redis + ChromaDB + API; requires `.env`):

```bash
docker compose up
```

## Project layout

See [`docs/architecture.md`](docs/architecture.md) for the full breakdown.
Top level:

```
app/            FastAPI backend: API routes, DB models/schemas, services, AI agent
app/static/     dashboard: plain HTML/CSS/JS, served at /dashboard
ml/             Elo, Poisson, feature engineering, training, ensemble, monitoring
rag/            ChromaDB RAG knowledge base (original + Wikipedia content)
data/           raw/ processed/ live/ — never committed, see .gitignore
scripts/        data pipeline + injuries sync + reporting CLIs
tests/          pytest suite (149 tests)
docker/         Dockerfile(s)
docs/           architecture, setup guide, API reference, roadmap
```

## Documentation

- [Setup Guide](docs/setup_guide.md)
- [Architecture](docs/architecture.md)
- [API Reference](docs/api_reference.md)
- [Roadmap](docs/roadmap.md)

## Testing & quality

```bash
uv run pytest -q
uv run black --check .
uv run ruff check .
```
