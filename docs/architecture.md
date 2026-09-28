# Architecture

## Data flow

```
Football-Data.co.uk CSVs
        │  scripts/download_data.py (real HTTP download, no auth)
        ▼
data/raw/*.csv
        │  scripts/clean_data.py (dedupe, normalize names, validate)
        ▼
data/processed/matches.csv
        │  scripts/load_to_db.py (upsert teams/matches, rebuild Elo history)
        ▼
Postgres / SQLite  (teams, matches, elo_history)
        │
        ├─▶ ml/training/train_match_result.py ──▶ ml/models/*.json (versioned)
        │        walk-forward features, time-based train/test split
        │        registers app.models.ModelVersion + TrainingRun
        │
        └─▶ app/services/prediction_service.py
                 fetches match + history + Elo + active model
                 │
                 ▼
             ml/prediction/predict.py
                 combines:
                   ml/elo/engine.py        (Elo-implied result probs)
                   ml/poisson/model.py     (Poisson-implied result probs,
                                             correct score, O/U 2.5, BTTS)
                   xgboost (if trained)    (learned result probs)
                 │
                 ▼
             ml/ensemble.py — weighted vote + confidence score
                 │
                 ▼
             app/models/Prediction + PredictionHistory (persisted)
                 │
                 ▼
             FastAPI response (app/api/routes_predict.py)
```

## Why three independent result estimators

- **Elo** captures long-run team strength cheaply and updates automatically
  after every match — no retraining needed, good as a stable baseline.
- **Poisson** models the actual goal-scoring process, which is what lets it
  also answer correct score / O-U / BTTS questions the other two can't,
  without inventing separate models for each (see below).
- **XGBoost** learns non-linear interactions between form, rest days, head-to-
  head history, etc. that neither Elo nor Poisson can see.

They're combined by weighted averaging in `ml/ensemble.py`
(`DEFAULT_WEIGHTS = {"elo": 0.25, "poisson": 0.35, "xgboost": 0.40}`). If no
XGBoost model has been trained yet, its weight is dropped and Elo/Poisson are
renormalized — `/predict` always returns a real answer, never a placeholder.

## Model 2 and 3: LightGBM Over/Under goals, Gradient Boosting BTTS

`ml/training/train_over_under.py` and `ml/training/train_btts.py` train
dedicated binary classifiers on the same leakage-safe features as the
match-result model. `ml/prediction/predict.py` blends each dedicated model's
probability with the Poisson-derived one (`DEDICATED_MODEL_WEIGHT = 0.6`)
whenever a model has been trained; if not, the Poisson probability is used
alone — `/predict` always returns a real answer either way, and reports
which path was taken: `btts_model_used` for BTTS, and a per-line
`model_used` flag inside `goals_markets` for Over/Under goals, which offers
two lines (1.5/2.5 — `ml.prediction.predict.GOALS_LINES`) and so trains one
model per line (`train_over_under.py --line`), exactly like corners/cards
below. Both
models are deliberately shallow (see the comments in their training scripts)
because the deeper config copied from the match-result model overfit ~900
training rows badly enough to produce a worse log-loss than a constant
baseline — a real tuning finding, not a stylistic choice.

The half-time goals (O/U 0.5), Corners (O/U 7.5/8.5/9.5) and Cards (O/U
2.5/3.5/4.5) markets all follow the identical
dedicated-model-blended-with-Poisson pattern per line
(`ml/training/train_ht_goals.py`, `ml/training/train_corners.py`,
`ml/training/train_cards.py` — 11 models total across all 6 markets) — see
"Half-time goals" and "Corners and cards" below for what's different about
them: their Poisson baseline can be genuinely unavailable, since not every
source records half-time scores or corner/card counts. Full-time goals are
the one stat every source in this pipeline records, so `goals_markets` and
BTTS never have to handle that case.

## Explainability (SHAP)

`ml/prediction/explain.py` runs `shap.TreeExplainer` on the active XGBoost
model for the specific scaled feature vector used in that prediction, and
returns the top 5 features that pushed the model toward its predicted
outcome. Best-effort: if no model is loaded or SHAP raises for any reason,
`explanation` is `null` rather than the request failing.

## Value detection

`ml/monitoring/value_detection.py` converts bookmaker decimal odds
(`Match.odds_home_win/draw/away_win`, ingested from Football-Data.co.uk's
market-average and Bet365 columns) to overround-adjusted implied
probabilities, and reports the percentage-point gap against the model's own
probability per outcome (`GET /value/{match_id}`). This is a mathematical
comparison only — never a profit guarantee (see
`rag/knowledge_base/value_betting_concepts.md`).

## Calibration and drift monitoring

`ml/monitoring/evaluation.py` backfills real match outcomes onto
`prediction_history` once matches complete. `ml/monitoring/calibration.py`
buckets evaluated predictions by their assigned probability and compares
against actual accuracy per bucket, plus a multi-class Brier score.
`ml/monitoring/drift.py` compares the two most recent `training_runs` for a
model and flags a >5-point accuracy drop or >0.10 log-loss increase
(`check_drift`), and separately compares each feature's mean between those
same two runs, flagging any that moved >0.5 standard deviations independent
of whether accuracy moved (`check_feature_drift` — needs
`ml.training.common.compute_feature_summary`'s mean/std snapshot, stored in
`training_runs.metrics["feature_summary"]` by every `ml/training/train_*.py`
script). `GET /model/monitoring` and `scripts/generate_report.py`
(matplotlib PNGs to `docs/reports/`) both read from these.

## Live standings

`app/services/standings_service.py` computes a standard league table
(played/won/drawn/lost/GF/GA/GD/points, standard tiebreakers) directly from
our own ingested `matches` rows — unlike injuries, this needs no external
feed at all, since we already ingest every result. `GET
/standings/{competition}` and the agent's `get_standings` tool both use it.

## Injuries

`scripts/sync_injuries.py` is the only piece of this codebase that calls a
paid/free-tier third-party API (API-Football, `API_FOOTBALL_KEY` required).
It resolves and caches each `Team.api_football_id` by name search, fetches
injuries for the auto-detected current season (`current_api_football_season`
— European seasons run roughly Aug-May, so before July it's still last
year's season), and replaces that team's `Injury` rows.

The live response shape needed two fixes discovered only once a real key
was available: `team`+`season` returns one row per missed *fixture*, not
one row per player (`_keep_latest_entry_per_player` collapses that to one
row per player, keeping the most recent — the best available proxy for
"still out," since the API has no resolved/recovered flag), and
`player.name` can be present-but-`null` in a real entry (checked as a
value, not just key presence). `Team.injuries_synced_at` tracks freshness;
`GET /injuries/{team}` and the agent's `get_injuries` tool both check it and
report `available: false` honestly (with instructions to run the sync)
rather than guessing for any team that's never been synced. Wired into
`app/scheduler.py`'s daily job, which skips itself (not a failure) when no
key is configured.

## ROI backtesting

`ml/monitoring/roi_backtest.py` simulates flat-staking every value edge
above a threshold, restricted to the exact same held-out test-period
matches the active model's own accuracy/log-loss are reported against
(`resolve_test_period_start` re-derives that cutoff from
`ml.training.common.time_based_split` on the same processed dataset).
Betting on matches the model trained on would be look-ahead bias and would
make the ROI number meaningless — this is the one guard that makes the
number honest. `GET /model/roi-backtest`.

## AI analyst agent

`app/agents/analyst.py` runs an Anthropic tool-calling loop
(`ANTHROPIC_API_KEY`, read via `get_settings()` — not raw `os.environ`, which
never sees `.env`-only values) over the tools in `app/agents/tools.py`, each
a thin wrapper over an already-tested service — the system prompt forbids
inventing any statistic not returned by a tool call. Both `get_injuries` and
`get_standings` are real (see above); `get_injuries` still honestly reports
unavailability per-team when nothing's been synced for it. Live-verified
with a real key (see `docs/roadmap.md`). See `app/agents/README.md`.

## RAG knowledge base

`rag/retriever.py` wraps a ChromaDB collection (local persistent store by
default, or the `chromadb` Docker service via `CHROMA_URL`), embedding with
Chroma's bundled all-MiniLM-L6-v2 model — no API key needed. Indexes both
original articles (`rag/knowledge_base/*.md`) and real Wikipedia content
(`rag/knowledge_base/wikipedia/*.md`, CC BY-SA 4.0, fetched and attributed by
`rag/ingestion/fetch_wikipedia.py`). The agent's `retrieve_knowledge` tool
queries it for methodology/background questions. See `rag/README.md`.

## Scheduler

`app/scheduler.py` wires `scripts/*` and `ml.training.*`/`ml.monitoring.*`
into APScheduler cron jobs (daily data refresh, 6-hourly prediction
evaluation, weekly retrain + report, monthly archive-candidate review). Off
by default (`ENABLE_SCHEDULER=false`) so tests and one-off script runs never
start background jobs; started from `app.main`'s FastAPI lifespan when
enabled.

## Dashboard

`app/static/dashboard/` is a plain HTML/CSS/vanilla-JS single-page app —
no build step, no Node.js — served by FastAPI itself (`app.main` mounts it
at `/dashboard` via `StaticFiles`). It calls the same JSON endpoints
everything else in this document describes; `GET /matches` and
`GET /competitions` (`app/api/routes_matches.py`) exist specifically to
support it, since nothing else lets a caller discover a `match_id` from
scratch. Charts are inline SVG following the `dataviz` skill's
categorical/sequential/diverging color roles (see the CSS custom
properties in `style.css`). See `app/static/dashboard/README.md`.

## Confidence score

`ml/ensemble.py::combine()`:

```
confidence = 100 * (0.6 * model_agreement + 0.4 * feature_completeness)
```

- `model_agreement` = 1 - mean pairwise total-variation distance between the
  Elo/Poisson/XGBoost result-probability vectors (1.0 = full agreement).
- `feature_completeness` = fraction of the "important" engineered features
  (form, rest days, Elo diff) that were non-null for this fixture (new teams
  with no history score lower).

## Leakage safety

`ml/feature_engineering/features.py` filters every input match list to
`match_date < target_date` internally, inside each `compute_*` function — so
even if a caller (by mistake) passes the entire dataset including future
matches, the output is identical to passing only prior matches. This is
directly tested in `tests/test_feature_engineering.py`.

The XGBoost training script (`ml/training/train_match_result.py`) reinforces
this at the pipeline level: it walks matches in chronological order, computing
each match's features and Elo-before-match *before* applying that match's
result to the Elo state, and splits train/test by time rather than randomly.

## Multi-sport schema

The `matches` table began as football-only and now holds three sports'
worth of shape. The discriminator is `matches.sport` (and `teams.sport`),
defaulting to `"football"` so the 62,568 rows that predated the change kept
their meaning without a backfill.

**`home_goals`/`away_goals` became `home_score`/`away_score`.** Not a
cosmetic rename: the column holds goals for football, points for basketball
and games won for tennis, and a name that says "goals" would be actively
wrong for two of the three. The migration (`c1d2e3f4a5b6`) does this as a
genuine `ALTER ... RENAME`, never an add-and-drop, because those columns
hold every ingested match ever loaded and a drop would discard them.

**`teams.name` lost its global UNIQUE in favour of `UNIQUE(sport, name)`.**
The same string can legitimately name a football club and a basketball
franchise, and merging them would fuse two unrelated rating histories. The
same hazard reappears anywhere a team is keyed by name rather than row id,
which is why `load_to_db.rebuild_elo_history` runs **one Elo engine per
sport** rather than one shared engine — a single name-keyed rating dict
would quietly undo the constraint. Ratings aren't comparable across sports
anyway, so a shared pool buys nothing even when names don't collide.

**The sport filter on prediction history is load-bearing.**
`prediction_service._all_completed_history` filters to the target match's
own sport. Without it, a ~113-point basketball game would be fed to a
Poisson goal model truncated at 8 goals — a silent corruption of every
football prediction, not a crash. Pinned by
`tests/test_multi_sport.py::test_prediction_history_is_scoped_to_one_sport`.

**What is deliberately *not* generalised yet:** the `predictions` and
`prediction_history` tables. They're shaped around football's three-way
outcome and goal markets, so a basketball prediction is served and cached
but not persisted (`prediction_service._predict_basketball` says so in
place). Writing one into those tables would mean inventing a draw
probability or leaving required columns empty; generalising them is a
schema change worth doing deliberately rather than as a side effect.

## International football

National-team football (World Cup, Euros, Nations League, Copa America,
AFCON and its qualifiers, friendlies) is the same sport as the domestic leagues, so it reuses the
entire pipeline — the same Elo, the same Poisson, the same features, the
same models. It is not a separate vertical. Two things genuinely differ:

**Neutral venues.** Tournament football is played on neutral ground, where
the "home" side is only a fixture-list label. Crediting it the Elo
home-advantage offset would systematically under-rate whichever side the
schedule listed second. `matches.neutral_venue` drives
`EloEngine._home_offset`, which returns zero for those matches — so an
evenly-rated pair on neutral ground is a true 50/50.

The flag is set per *competition* (`clean_data.NEUTRAL_VENUE_COMPETITIONS`):
World Cup, Euros, Copa America and the Africa Cup of Nations are neutral;
the Nations League, **AFCON qualifiers** and friendlies are genuinely
home-and-away and are not. AFCON is the clearest illustration of why this is
per-competition rather than per-competition-*family*: the finals are one
host nation's tournament, while the qualifiers that feed it are ordinary
home-and-away fixtures, so the two halves of the same competition get
opposite flags. This carries one known,
bounded approximation: the **host nation's own matches** at a tournament
really are home games and are marked neutral anyway — a handful per edition.
The ingested 2023 AFCON final (Nigeria 1-2 Ivory Coast, played in Ivory
Coast) is exactly this case.
Erring toward neutral is the safer direction, since it declines to credit an
advantage rather than inventing one.

The Poisson side needs no equivalent fix: it's already fitted per
competition (see "Multi-league support" above), so a competition whose
matches are all neutral learns near-equal home/away scoring rates from its
own data.

**Tournament years aren't split seasons.** A World Cup is one calendar year,
filed as `WC_2022.csv`, while a domestic season is `E0_2324.csv`. Both are
four digits and all numeric, so `clean_data._season_label` tells them apart
by whether the halves are consecutive — `23`->`24` is a season, `20`->`22`
is not. Without this a World Cup would be labelled "2020-2022".

Source: API-Football, one request per competition-season (~30 total), since
Football-Data.co.uk publishes domestic leagues only. A **free** plan serves
seasons 2022-2024 and rejects older ones with a `plan` error, which
`fetch_international.py` skips rather than treating as a failure — so a
free-tier run still ingests everything it's entitled to. A paid plan widens
the season lists in `COMPETITIONS` and nothing else changes.

## Basketball

Basketball shares the `matches` table, Elo, and the leakage-safe history
index — and essentially nothing else, because the sport differs in ways that
are structural rather than parametric:

- **No draws.** Of 4,149 ingested NBA games, **zero** were ties; the league
  plays overtime until someone wins. So the winner model is binary
  (`train_basketball_winner.py`), not the football model's three-class head,
  which would be asked to predict a class that never occurs. The prediction
  output has no `draw` field at all, and `home_win + away_win` sums to 100
  on its own. `EloEngine.result_probabilities` is likewise bypassed — it
  deliberately carves a draw band out of the Elo expectation, which is right
  for football and wrong here, so the basketball path uses the raw two-way
  `expected_score`.
- **No Poisson baseline.** NBA games average **227.3 total points** against
  a football Poisson fit truncated at 8 goals. There is no reuse to be had,
  so the totals markets are the dedicated model alone — and an untrained
  line is genuinely unpredictable rather than degraded, reporting
  `prob_over: null` instead of deriving a number from expected totals.
- **Rest matters.** `rest_days` and `is_back_to_back` are real basketball
  features with no football equivalent (an NBA team plays on consecutive
  nights; a league footballer essentially never does). Rest is capped at 14
  days so a season opener reads as "maximally rested" rather than encoding
  "start of season".

Markets: match winner, plus total points at 215.5 / 225.5 / 235.5. Those
lines came from the ingested distribution, not from guesswork — the mean is
227.3 and the median 227, and 225.5 splits the data at 53.2% over, which is
why it's the real bookmaker centre line.

**The totals models are reported with a base-rate baseline, and it matters.**
Raw accuracy flatters an outer line, because a line far from 50/50 is an
easier binary problem. Measured against "always guess the majority class":

| Line | Accuracy | Majority-class baseline | Real edge |
|---|---|---|---|
| 215.5 | 71.91% | 71.67% | +0.24pp — none to speak of |
| 225.5 | 59.81% | 54.72% | **+5.1pp** |
| 235.5 | 66.59% | 65.38% | +1.2pp |

Only the centre line adds real value. The outer two are recorded honestly
rather than quoted at their headline accuracy, which is exactly what
`majority_class_base_rate` in each run's metrics exists to expose. The
winner model, by the same yardstick, scores 64.89% against a 54.12%
always-pick-home baseline — a genuine ~11-point edge.

Source: API-Basketball (same api-sports key as football, different host).
There is no `clean_data` step: that script exists to reconcile 18 leagues of
inconsistent CSV dialects, and one already-consistent JSON API has no
dialect to reconcile.

## Tennis

Tennis shares the `matches` table and the leakage-safe history index, and
almost nothing else. Four things drive the design, and each one is a place
where doing the obvious thing would have produced a broken model.

**1. Winner/loser leakage — the trap this sport is famous for.**
The source records a `Winner` and a `Loser` column, not "player 1" and
"player 2". Loading those straight into `home_team`/`away_team` would mean
the home player won 100% of matches, and a model trained on it would report
perfect accuracy while having learned only "home always wins". So
`scripts/fetch_tennis.py` assigns the two players to slots by a
**deterministic hash of the match's identity** (`_slot_swap`): the label
splits ~50/50, and it is stable across re-ingests, so re-running the
importer doesn't silently relabel history and invalidate trained models. The
measured home-slot win rate is **49.98%**, and the winner trainer records it
in its metrics every run so a regression here shows up immediately.

Because the slots are a hash rather than a venue, every tennis row is stored
`neutral_venue=True` and no home-advantage term appears anywhere in the
tennis path. Adding one would be modelling a hash function.

**2. Sets decide the match; games only describe it.** A tennis player can
win fewer games than their opponent and still win the match. On the ingested
data a games-based winner label would be **wrong for 2.00%** of matches and
**undefined (an exact tie) for another 2.82%** — 4.81% corrupted labels. So
`home_score`/`away_score` hold *sets*, which keeps "the higher score won"
true in every sport in this database, and total games live in
`home_games`/`away_games` to price the totals market.

**3. Skill is surface-specific.** A player's clay ability is genuinely a
different quantity from their hard-court ability. `SurfaceElo`
(`ml/feature_engineering/tennis.py`) therefore keeps an overall pool *and* a
pool per surface, and both are offered as features rather than blended for
the model in advance. This is also why the tennis prediction path rebuilds
ratings by replaying history instead of reading `elo_history`: that table
stores one rating per competitor, which cannot express "1900 on clay, 1650
on grass".

**4. `best_of` is not cosmetic.** WTA is always best-of-3 and averages 21.8
total games; ATP plays best-of-5 at Grand Slams and averages 25.9. A totals
model blind to the format would systematically under-price a men's Slam, so
the format is stored and fed as a feature.

**Results, against baselines that make them honest.** The winner market is
dominated by rating difference, so the baseline worth beating is "always
pick the higher-Elo player", not "always pick home" (which is a coin flip
here by construction):

| Market | Accuracy | Baseline | Real edge |
|---|---|---|---|
| Winner | 64.62% | 64.22% (Elo) | +0.40pp — inside noise |
| Total games 19.5 | 67.37% | 66.72% (majority class) | +0.65pp |
| Total games 21.5 | 59.90% | 55.15% | **+4.75pp** |
| Total games 23.5 | 64.90% | 55.88% | **+9.02pp** |

The winner model is **not** meaningfully better than a plain Elo rule: on
13,716 test matches the standard error is ~0.41pp, so +0.40pp is
indistinguishable from zero. That is reported rather than hidden, and it is
a real finding about the sport — tennis outcomes are close to fully
described by rating difference. The totals markets are where the model earns
its place, because Elo ranks players but says nothing about how *long* a
match runs.

Source: tennis-data.co.uk, the same publisher as the football-data.co.uk
feed 16 of the domestic leagues already come from. It also ships bookmaker
odds, which feed the existing value-detection and ROI paths. The originally
intended source (Jeff Sackmann's ATP/WTA repos) had become unavailable — see
docs/roadmap.md.

## Multi-league support

Ingesting several leagues together (the default dataset is 18 leagues × 10
seasons, 62,568 matches — the "big 5" top flights plus their second
divisions, Eredivisie, Belgian Pro League, Primeira Liga, Süper Lig, Greek
Super League, the Scottish Premiership, MLS, and the Saudi Pro League — see
"Non-native data sources" below for the last two) surfaced two real
correctness issues that a single-league dataset never exposed:

- **Poisson baseline blending.** `ml.prediction.predict.predict_match` takes
  an optional `competition` and filters the matches it fits `PoissonModel`
  on to that same competition — leagues have genuinely different
  goal-scoring and home-advantage baselines, and fitting one shared
  "league average" across all of them would silently corrupt the
  expected-goals estimate for every league, not just add noise.
  `competition=None` keeps the old unscoped behavior for callers that don't
  have one.
- **No league signal for the ML models.** `ml.training.common.one_hot_competition`
  adds a fixed one-hot column per known league (`KNOWN_COMPETITIONS`) to
  `FEATURE_COLUMNS`, so XGBoost/LightGBM/GBM can actually learn
  league-specific patterns instead of averaging over incompatible ones. An
  unrecognized competition encodes as all-zero rather than raising.

Both are covered in `tests/test_multi_league.py`, including a test that
deliberately mixes a high-scoring and a low-scoring synthetic league and
confirms competition-scoping keeps their expected-goals estimates properly
separated.

## Non-native data sources

16 of the 18 leagues come straight from Football-Data.co.uk's regular
per-season CSVs (`scripts/download_data.py`). The other two needed a real
source decision each, checked directly rather than assumed:

- **MLS** is on Football-Data.co.uk too, but under a different publishing
  convention (`data.php`'s "extra" countries) — one file per country
  covering every season at once, with different column names
  (`Home`/`Away`/`HG`/`AG` instead of `HomeTeam`/`AwayTeam`/`FTHG`/`FTAG`)
  and no shots/corners/cards columns. `scripts/fetch_extra_league.py`
  downloads that one file, filters to the requested seasons (and league,
  for a country with more than one), remaps columns onto the standard
  names, and writes one CSV per season into `data/raw/` — indistinguishable
  from `download_data.py`'s own output to everything downstream. MLS also
  runs within a single calendar year rather than spanning two like the
  European leagues, so its season code is a same-year pair (`2424`, not
  `2425`) rather than a bug.
- **The Saudi Pro League isn't on Football-Data.co.uk at all** — confirmed
  directly against their published country list
  (`https://www.football-data.co.uk/data.php`), not assumed from its
  absence in our own config. `scripts/fetch_api_football_league.py` sources
  it from API-Football's `/fixtures` endpoint instead (league id 307,
  seasons 2016-2025 confirmed available), pulling only date/teams/goals —
  enough for the match-result/O-U/BTTS features and markets — and writing
  the same standard per-season CSV shape. Deliberately *not* pulled: shots/
  corners/cards (each would need a separate `/fixtures/statistics` call per
  fixture, i.e. ~2,500 extra requests) and odds (same problem, `/odds` per
  fixture, only used for value detection anyway). The practical effect: the
  Saudi Pro League (and MLS, whose Football-Data.co.uk file also has no
  corners/cards columns) gets full match-result/O-U/BTTS treatment but no
  Corners/Cards market — see "Corners and cards" below for how that's
  reported (`None`, not a fabricated number). This needs a paid-tier
  `API_FOOTBALL_KEY`; the free tier's daily request quota can't
  realistically cover ~10 seasons of `/fixtures` calls.

Both adapters converge on the same `data/raw/{code}_{season}.csv` shape
`download_data.py` produces, so `clean_data.py`, `load_to_db.py`, and every
downstream consumer need no awareness that these two leagues came from a
different source — the one-hot/Poisson-scoping fixes above apply to them
identically. Live-verified: real `/predict` calls on both a Saudi Pro
League and an MLS match returned sensible predictions whose SHAP
explanations correctly cited that match's own `competition_*` feature.

## Half-time goals

A new market (O/U 0.5 half-time goals — `ml.prediction.predict.HT_GOALS_LINES`)
off a column that, like corners/cards, was ingested long before anything
consumed it: `home_ht_goals`/`away_ht_goals` on `app/models/match.py`.

**It gets its own Poisson fit, not a halved full-time one.** The obvious
shortcut — take the fitted full-time expected goals and halve them — would
be wrong, and not just imprecisely so: teams genuinely set up differently
across the two halves (second halves score more, and substitutions/game
state only exist in the second), so a half is not "half a match"
statistically. `ml.prediction.predict` therefore fits a second,
independent `PoissonModel` on half-time scores specifically
(`_fit_count_stat_poisson` with `_ht_goals_value`, `HT_GOALS_MAX = 10`) —
the same legitimate reuse of `PoissonModel` described for corners/cards
below, applied to a real goal-scoring process rather than a
goal-*like* count stat.

**Availability is per stat, not per league** — this market is what makes
that distinction visible. Half-time score is recorded for 58,053 of 62,568
matches (92.8%). Of the 4,515 without it, 4,445 are the entirety of MLS,
whose Football-Data.co.uk file has no `HTHG`/`HTAG` columns at all (see
"Non-native data sources" above); the other 70 are scattered individual
gaps across 10 leagues that do otherwise record it. The
Saudi Pro League *does* have it, even though it has no corner/card data,
because `scripts/fetch_api_football_league.py` reads half-time scores from
the same `/fixtures` response it already reads full-time scores from. So a
Saudi match serves real goals *and* half-time goals lines while reporting
corners/cards as unavailable, and an MLS match serves only its goals
lines — each market's availability is decided by that market's own stat,
not by a per-league allowlist. Rows with no `total_ht_goals` value are
dropped before training, the same as any row missing its label.

## Corners and cards

Two additions built together, since they share the same real gap and the
same fix: `home_corners`/`away_corners`/`*_yellow_cards`/`*_red_cards` were
ingested from day one (`app/models/match.py`) but never used anywhere.

**As an input feature.** `ml.feature_engineering.features.compute_corner_form`
adds rolling per-team corners-won/corners-conceded averages
(`home_avg_corners_won`, `home_avg_corners_conceded`, and the away
equivalents) to `FEATURE_COLUMNS`, so the match-result/O-U/BTTS models get
this signal too, not just the two new markets below. Not every league or
season records corners — Belgian Pro League, Dutch Eredivisie, French
Ligue 2, German 2. Bundesliga, Greek Super League, Italian Serie B,
Portuguese Primeira Liga, Spanish Segunda Division, and Turkish Süper Lig
are ~77-82% covered rather than 100%, and MLS/Saudi Pro League are 0% (see
"Non-native data sources" above) — a match missing the stat is *skipped*
from the rolling average, not treated as zero corners, which would
understate a team's real rate. Overall: 49,556 of 62,568 matches (79.2%)
have corner/card data.

**As two new multi-line markets.** Corners offers three real bookmaker
lines (7.5, 8.5, 9.5 — `ml.prediction.predict.CORNERS_LINES`), Cards three
more (2.5, 3.5, 4.5 — `CARDS_LINES`); none picked to make the data look
clean — the 9.5/4.5 "center" lines split our own data almost exactly in
half (51.0%/44.4% over), which is *why* real bookmakers use them as the
primary line, and the outer lines were specifically requested to widen
coverage beyond that single line. Each line is a genuinely distinct
market ("Over 8.5" isn't derivable from "Over 9.5"), so each gets its own
trained classifier — `ml.training.train_corners --line 8.5`,
`ml.training.train_cards --line 3.5`, etc. — registered under its own
model name (`model_name_for_line`, e.g. `lightgbm_over_under_corners_8_5`).

The Poisson baseline is different: it's **one fit per stat, reused across
every line**. `ml.prediction.predict._fit_count_stat_poisson` reuses
`PoissonModel` exactly as-is: corners and cards are, like goals,
non-negative per-match count stats with a real team-level "strength"
structure, so relabeling a match's corner/card counts onto `PoissonModel`'s
`home_goals`/`away_goals` fields and fitting it is statistically
legitimate, not a hack — a wider truncation bound is used (`max_goals=15`
for corners, `10` for cards, vs. goals' default `8`, since totals run
higher). `_build_market_lines` then calls that one fitted model's
`prob_over_under(line=...)` once per offered line — a real, distinct
calculation each time off the same scoreline matrix — and blends each
line's result with that line's own dedicated model, the same way the
O/U-goals and BTTS models blend (`DEDICATED_MODEL_WEIGHT = 0.6`). A line
with no trained model for it just falls back to the Poisson number alone,
same as any other untrained dedicated model.

**Genuine unavailability, not a fabricated number.** When a competition has
*zero* corner/card history at all (MLS, Saudi Pro League), there's no
Poisson baseline to fit — rather than surface a number computed from an
all-zero-filled feature vector (which would look like a real prediction but
carry no signal), every line of both markets reports `prob_over`/
`prob_under` as `None` (`corners_markets`/`cards_markets` on
`PredictionOut`, each a list of `{line, prob_over, prob_under, model_used}`
— see `docs/api_reference.md`), and the dashboard shows "N/A" per line.
`model_used` reflects whether that specific line's dedicated model actually
contributed, not just whether a trained artifact exists for it — a
loaded-but-unused model on a `None` line would be a misleading flag.
Covered end-to-end in `tests/test_corners_and_cards.py`, including a
Poisson-scoping regression test (mirroring `tests/test_multi_league.py`'s)
that deliberately mixes a high-corner and a low-corner synthetic league and
confirms they stay properly separated, and a test that the three corners
lines are genuinely distinct, monotonically-decreasing calculations rather
than all collapsing to the same number.

## Feature-engineering performance at scale

`ml/feature_engineering/features.py`'s `compute_*` functions originally
scanned the *entire* match list on every call (`O(n)` per lookup, ~9 lookups
per match). That's fine for a single prediction, but `build_feature_frame`'s
walk-forward loop calls them once per match in the whole training set —
without a fix, that's `O(n²)` overall, measured at **~56 minutes** for an
18,000-match run. `TeamHistoryIndex` (`build_team_history_index`) groups
matches per team once, up front (`O(n)`), so each lookup becomes an
`O(log k)` bisect against that team's own match list (k, order of hundreds)
instead of a scan of the whole dataset (n, order of tens of thousands) —
**~15 seconds** for that same 18,000-match run. Every function still accepts
a plain `list[dict]` unchanged (the index is opt-in, detected via
`isinstance`), so existing callers/tests are unaffected;
`ml.training.common.build_feature_frame` and `ml.prediction.predict.predict_match`
both build the index once and reuse it. `tests/test_feature_engineering.py`
asserts the index path produces byte-for-byte identical, still leakage-safe
output to the plain-list path — the optimization changes *how fast* lookups
are, never *what* they return.

Re-measured after expanding to 16 leagues / 55,641 matches: feature-frame
construction took ~66 seconds — roughly 4x the time for ~3x the data,
consistent with the expected `O(n log k)` scaling (more teams means each
team's own per-team match list, `k`, also grows, so it's not perfectly
linear in `n`). Re-measured again after adding MLS and the Saudi Pro League
(18 leagues / 62,568 matches): **~54 seconds** — actually *down* from the
16-league measurement despite more matches, which is within the noise of
this kind of wall-clock measurement (Python/XGBoost/LightGBM process
startup overhead is a fixed cost per run, not part of the scaling curve)
rather than a real speedup. Still nowhere close to `O(n²)`: naively scaling
the old unindexed ~56-minutes-at-18k baseline to this dataset size would predict
somewhere around 8-9 *hours*, not one minute.

## Database

SQLAlchemy models in `app/models/`, portable across SQLite (tests/local dev)
and Postgres (docker-compose) — no Postgres-only types (e.g. JSONB) are used.
Alembic (`alembic/`) manages schema migrations; `DATABASE_URL` is the only
thing that changes between environments.

## Caching

`app/utils/cache.py` wraps Redis and is a safe no-op if Redis isn't running —
tests set `REDIS_URL=""` and never touch the network. `/predict` results are
cached for 10 minutes per match.
