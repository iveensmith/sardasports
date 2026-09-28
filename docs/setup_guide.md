# Setup Guide

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python package/version manager). If you
  don't have it: `pip install uv` or see the uv docs for your platform.
- Docker + Docker Compose, only if you want to run Postgres/Redis in
  containers instead of local SQLite.

## 1. Environment

```bash
uv python install 3.12
uv venv --python 3.12
uv sync                 # installs runtime + dev dependencies from pyproject.toml
cp .env.example .env
```

The default `.env` uses SQLite (`sqlite:///./data/uniquepredict.db`) — no
Postgres/Redis required to get started. To use Postgres, uncomment the
`DATABASE_URL` line for it in `.env.example` (or start it via
`docker compose up postgres`) and point `.env` at it.

## 2. Get real data

The default dataset is 18 leagues x 10 seasons (62,568 matches): 16 from
Football-Data.co.uk directly — the "big 5" top flights (Premier League, La
Liga, Bundesliga, Serie A, Ligue 1) plus their second divisions, plus
Eredivisie, Belgian Pro League, Primeira Liga, Süper Lig, Greek Super
League, and the Scottish Premiership — plus MLS and the Saudi Pro League
via two adapter scripts (below), since neither fits `download_data.py`'s
assumptions. This much history lets the Poisson/ML models learn real
per-league baselines rather than noisy small-sample ones, and covers every
league a `/predict` call is likely to be made against with real per-league
signal rather than the generic Elo+Poisson fallback (see
`docs/architecture.md`'s "Multi-league support" section for what that
fallback is and when it kicks in). Downloading is per-league, so loop over
whichever leagues you want:

```bash
for LEAGUE in E0 E1 SP1 SP2 D1 D2 I1 I2 F1 F2 N1 B1 P1 T1 G1 SC0; do
  uv run python scripts/download_data.py --league $LEAGUE --seasons 1516,1617,1718,1819,1920,2021,2122,2223,2324,2425
done

# MLS: also on Football-Data.co.uk, but as one all-seasons file with
# different column names — fetch_extra_league.py normalizes it into the
# same per-season shape as the loop above.
uv run python scripts/fetch_extra_league.py --country USA --league MLS --code MLS1 \
  --seasons 2016,2017,2018,2019,2020,2021,2022,2023,2024,2025

# Saudi Pro League: not on Football-Data.co.uk at all (checked directly —
# it's absent from their full country list). Sourced from API-Football's
# /fixtures instead; needs a paid-tier API_FOOTBALL_KEY in .env; the free
# tier's daily quota can't realistically cover ~10 seasons of history.
uv run python scripts/fetch_api_football_league.py --league-id 307 --code SAU1 \
  --seasons 2016,2017,2018,2019,2020,2021,2022,2023,2024,2025

uv run python scripts/clean_data.py
uv run python scripts/load_to_db.py
```

- `download_data.py` pulls free CSVs from Football-Data.co.uk. `--league`
  accepts any of their league codes — see `KNOWN_LEAGUES` in
  `scripts/download_data.py` for the full list (E0 = EPL, SP1 = La Liga,
  D1 = Bundesliga, I1 = Serie A, F1 = Ligue 1, E1 = Championship, plus the
  10 more above); `--seasons` is comma separated `YYZZ` codes, e.g.
  `2324` = 2023-2024. A single league/season
  (e.g. just `--league E0 --seasons 2425`) works fine too — it's a smaller,
  faster dataset to iterate with, just with lower accuracy (see
  `docs/architecture.md`'s "Multi-league support" section for why mixing
  leagues needs more than just more rows).
- `fetch_extra_league.py` and `fetch_api_football_league.py` handle leagues
  that don't fit `download_data.py`'s one-file-per-season assumption — see
  each script's module docstring for exactly why, and
  `docs/architecture.md`'s "Non-native data sources" section for the
  general pattern (both write into `data/raw/` in the same shape
  `download_data.py` does, so `clean_data.py` doesn't need to know the
  difference).
- `clean_data.py` normalizes team names, dedupes, validates, and writes
  `data/processed/matches.csv`.
- `load_to_db.py` upserts teams/matches and rebuilds the entire Elo history
  by replaying every completed match in chronological order.

Re-running all three is safe (idempotent): re-downloading overwrites the raw
files, re-cleaning re-derives the processed file, and `load_to_db.py` skips
matches it has already inserted (matched by a stable `external_id`).

## 3. Train the models

```bash
uv run python -m ml.training.train_match_result
uv run python -m ml.training.train_over_under
uv run python -m ml.training.train_btts

# Corners and cards are multi-line markets — each line (see
# ml.prediction.predict.CORNERS_LINES/CARDS_LINES) is its own genuine
# market with its own model, so train each one explicitly:
for LINE in 7.5 8.5 9.5; do uv run python -m ml.training.train_corners --line $LINE; done
for LINE in 2.5 3.5 4.5; do uv run python -m ml.training.train_cards --line $LINE; done
```

Each requires at least 100 matches in `data/processed/matches.csv` by
default (`--min-matches` to change it). Trains on the earliest ~80% of
matches by date, evaluates on the most recent ~20%, and prints accuracy/
log-loss. Writes a versioned artifact to `ml/models/` and registers it in
the `model_versions`/`training_runs` tables — none of the 9 (3 fixed +
3 corners lines + 3 cards lines) ever overwrite a previous model.
`/predict` works with any subset trained (it falls back to Elo+Poisson,
or for corners/cards just the Poisson baseline, for whichever aren't
trained) — the corners/cards markets specifically also need a competition
with real corner/card history to produce anything for *any* line (see
`docs/architecture.md`'s "Corners and cards" section); without it, every
line's `prob_over`/`prob_under` in `corners_markets`/`cards_markets` comes
back `null`, not an error.

## 3b. Index the RAG knowledge base (optional, for the AI analyst)

```bash
uv run python -m rag.ingestion.fetch_wikipedia   # (re-)fetch real Wikipedia articles
uv run python -m rag.indexer                     # index everything into ChromaDB
```

Indexes `rag/knowledge_base/**/*.md` (original articles + the real,
CC BY-SA-attributed Wikipedia articles) into a local ChromaDB store. No API
key needed (embeddings run locally). Safe to re-run either command.

## 3c. Enable the AI analyst agent (optional)

Add your own key to `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Without it, `POST /analyst/{match_id}` returns `503` and the rest of the API
is unaffected.

## 3d. Sync injuries (optional, for get_injuries)

```bash
uv run python scripts/sync_injuries.py --team Arsenal
uv run python scripts/sync_injuries.py --league "English Premier League"
```

Requires `API_FOOTBALL_KEY` in `.env` (free tier at
dashboard.api-football.com/register). Without it, `GET /injuries/{team}` and
the agent's `get_injuries` tool return `available: false` with instructions
to sync — never a guess. Not every league/season has injury coverage on the
free tier; check the `coverage.injuries` flag on that league's `/leagues`
response if a sync returns 0 entries unexpectedly.

## 4. Run the API

```bash
uv run uvicorn app.main:app --reload
```

Visit `http://localhost:8000/dashboard` for the dashboard (matches,
predictions, standings, team lookup, model monitoring — plain HTML/JS, no
separate process), or `http://localhost:8000/docs` for interactive OpenAPI
docs. Try the API directly:

```bash
curl http://localhost:8000/fixtures/today
curl http://localhost:8000/elo/Arsenal
curl http://localhost:8000/predict/1
curl http://localhost:8000/value/1              # needs a match with bookmaker odds
curl http://localhost:8000/model/monitoring
curl http://localhost:8000/standings/English%20Premier%20League
curl http://localhost:8000/injuries/Arsenal     # needs a sync first (step 3d)
curl -X POST http://localhost:8000/analyst/1    # needs ANTHROPIC_API_KEY
```

## 4b. Generate a calibration/drift report

```bash
uv run python scripts/generate_report.py
```

Backfills actual results onto `prediction_history`, then saves a calibration
chart to `docs/reports/`. Needs some completed, evaluated predictions to be
meaningful — call `/predict` on a few historical (already-completed) matches
first if you're just getting started.

## 4c. Scheduler (optional)

Set `ENABLE_SCHEDULER=true` in `.env` before starting the API to run the
daily/weekly/monthly jobs in `app/scheduler.py` automatically. Leave it
`false` (the default) for scripts, tests, and one-off local runs.

## 5. Docker Compose (Postgres + Redis + API)

```bash
docker compose up
```

`.env` must exist (Docker Compose reads it for `POSTGRES_*` vars; the `api`
service overrides `DATABASE_URL`/`REDIS_URL` to point at the `postgres`/
`redis` containers by service name). Run the data pipeline and training
commands above with `docker compose exec api uv run python scripts/...`
instead of `uv run ...` once the stack is up, so they write to the
containerized Postgres.

## 6. Tests & quality

```bash
uv run pytest -q
uv run black --check .
uv run ruff check .
```

Tests run against a throwaway local SQLite file and never touch Redis or the
network (see `tests/conftest.py`).

## 7. Database migrations (Alembic)

```bash
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

`alembic/env.py` reads `DATABASE_URL` from the same settings as the app, so
migrations always target whatever `.env` points at.
