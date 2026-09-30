# API Reference

Base URL: `http://localhost:8000`. Interactive docs at `/docs` (Swagger UI)
and `/redoc`. A dashboard at `/dashboard` (plain HTML/JS, no build step —
see `app/static/dashboard/README.md`) is built on these same endpoints if
you'd rather click through the data than call it directly. All API
responses are JSON; errors follow FastAPI's standard `{"detail": "..."}`
shape with an appropriate HTTP status code.

## `GET /health`

Liveness check. `{"status": "ok", "env": "development"}`.

## `GET /matches`

Browse/search matches — the only way to discover a `match_id` without
already knowing one. Query params: `competition`, `season`, `team`,
`opponent`, `status` (`scheduled`|`completed`), `limit` (default 50, max
200), `offset`. Unknown `team` (or `opponent`) returns an empty list, not
an error.

`opponent` only applies alongside `team` — it narrows to matches between
those two specific sides, either one at home, which is how the match
page's head-to-head tab is built (`GET /matches?team=Arsenal&opponent=Chelsea`).
`opponent` with no `team` is ignored rather than guessed at.

```json
{
  "count": 1140, "limit": 50, "offset": 0,
  "matches": [{"match_id": 1133, "match_date": "2025-05-25T00:00:00", "competition": "English Premier League",
    "season": "2024-2025", "home_team": "Southampton", "away_team": "Arsenal",
    "home_goals": 1, "away_goals": 2, "status": "completed", "has_odds": true}]
}
```

## `GET /competitions`

Every ingested competition and its seasons, with match counts — populates
the dashboard's filter dropdowns.

```json
{"competitions": [{"competition": "English Premier League", "seasons": ["2022-2023", "2023-2024", "2024-2025"], "match_count": 1140}]}
```

## `GET /fixtures/today`

Query params: `on_date` (optional, `YYYY-MM-DD`, defaults to today UTC).

```json
{
  "date": "2026-09-22",
  "count": 1,
  "fixtures": [
    {"match_id": 42, "match_date": "2026-09-22T15:00:00", "competition": "English Premier League",
     "home_team": "Arsenal", "away_team": "Chelsea", "status": "scheduled"}
  ]
}
```

## `GET /predict/{match_id}`

The full ensemble prediction. 404 if the match doesn't exist.

```json
{
  "match_id": 42, "home_team": "Arsenal", "away_team": "Chelsea",
  "match_date": "2026-09-22T15:00:00", "competition": "English Premier League",
  "match_status": "completed", "match_score": {"home": 2, "away": 1}, "ht_score": {"home": 1, "away": 0},
  "odds_1x2": {"home": 2.1, "draw": 3.3, "away": 3.4},
  "home_win": 54.2, "draw": 24.8, "away_win": 21.0,
  "expected_goals_home": 1.8, "expected_goals_away": 1.1,
  "top_scorelines": [{"score": "2-1", "probability": 0.11}, "..."],
  "btts_yes": 52.1, "btts_no": 47.9,
  "goals_markets": [
    {"line": 1.5, "prob_over": 76.7, "prob_under": 23.3, "model_used": true},
    {"line": 2.5, "prob_over": 52.2, "prob_under": 47.8, "model_used": true}
  ],
  "ht_goals_markets": [
    {"line": 0.5, "prob_over": 70.9, "prob_under": 29.1, "model_used": true}
  ],
  "corners_markets": [
    {"line": 7.5, "prob_over": 78.4, "prob_under": 21.6, "model_used": true},
    {"line": 8.5, "prob_over": 66.9, "prob_under": 33.1, "model_used": true},
    {"line": 9.5, "prob_over": 55.7, "prob_under": 44.3, "model_used": true}
  ],
  "cards_markets": [
    {"line": 2.5, "prob_over": 71.2, "prob_under": 28.8, "model_used": true},
    {"line": 3.5, "prob_over": 52.6, "prob_under": 47.4, "model_used": true},
    {"line": 4.5, "prob_over": 36.8, "prob_under": 63.2, "model_used": true}
  ],
  "confidence": 74.5, "confidence_label": "Medium",
  "model_version": "20260922T101500Z",
  "model_weights_used": {"elo": 0.25, "poisson": 0.35, "xgboost": 0.4},
  "btts_model_used": true,
  "explanation": [{"feature": "elo_diff", "impact_percentage_points": 6.1}, "... up to 5"],
  "actual_stats": {
    "shots": {"home": 14, "away": 9}, "shots_on_target": {"home": 6, "away": 3},
    "corners": {"home": 7, "away": 4}, "yellow_cards": {"home": 2, "away": 3}, "red_cards": {"home": 0, "away": 0},
    "possession": {"home": 58, "away": 42}, "offsides": {"home": 1, "away": 2}, "fouls": {"home": 9, "away": 11}
  },
  "events": [
    {"minute": 23, "added_time": null, "side": "home", "player": "B. Saka", "assist": "M. Ødegaard",
     "detail": "Normal Goal", "home_score_after": 1, "away_score_after": 0}
  ],
  "generated_at": "2026-09-22T09:00:00Z"
}
```

`match_status`/`match_score`/`odds_1x2` are read straight off the match
row, the same numbers the board shows — added so the fixture page carries
"what's actually true right now" alongside the prediction, which it
previously didn't at all. `ht_score`, `actual_stats` and `events` are
football-only.

`actual_stats` is `null` until `scripts/fetch_match_stats.py` has actually
tried this fixture (`stats_fetched_at` set on the row) — genuinely
different from a completed match whose competition reports none of these
stats, which instead comes back with every field present and `null`.
`events` is the goal-by-goal timeline (own goals and penalties included,
missed penalties excluded — they aren't goals), synced from the same
script; an empty list means no events are on record, not that nothing was
scored. Neither is ever fabricated: both are exactly what API-Football's
`/fixtures/statistics` and `/fixtures/events` reported, or absent.

`btts_model_used` reports whether the dedicated Gradient-Boosting model
(vs. the Poisson-only baseline) contributed to `btts_yes`; the four
multi-line markets carry the equivalent flag per line instead (see below).
`explanation` is the top-5 SHAP
feature contributions to the predicted outcome from the active XGBoost
model, `null` if no match-result model has been trained yet.

`goals_markets`/`ht_goals_markets`/`corners_markets`/`cards_markets` each
list one entry per offered line (`ml.prediction.predict.GOALS_LINES` =
1.5/2.5/3.5, `HT_GOALS_LINES` = 0.5, `CORNERS_LINES` = 7.5/8.5/9.5,
`CARDS_LINES` = 2.5/3.5/4.5 — each its own genuine market with its own
trained model, not one number the API interpolates between). A line's
`model_used` is per-line: a competition might have enough data for the
Poisson baseline but no trained model for that specific line. `prob_over`/
`prob_under` can be `null` for *every* line of a market, and availability
is **per stat, not per league** — the Saudi Pro League, for instance,
serves real goals *and* half-time goals lines while reporting corners and
cards as unavailable, because its source supplies half-time scores but no
corner/card counts; MLS's source supplies neither, so only its goals lines
are real. A competition with zero history for a stat gets every line of
that market reported as genuinely unavailable, never a fabricated number.
See `docs/architecture.md`'s "Half-time goals" and "Corners and cards"
sections.

Cached for 10 minutes per match (Redis if available, otherwise recomputed
every call — see `app/utils/cache.py`). Every call also appends a row to
`prediction_history`, which is what `/history/{match_id}` reads.

`match_status`/`match_score`/`odds_1x2` also appear on the basketball and
tennis responses below (read off the same match row), but `ht_score`,
`actual_stats` and `events` are football-only — there is no comparable
statistics/events feed wired up for the other two sports.

### Basketball responses

`/predict/{match_id}` returns a **different shape** for a basketball match,
discriminated by the `sport` field:

```json
{
  "match_id": 64300, "sport": "basketball",
  "home_team": "Oklahoma City Thunder", "away_team": "Indiana Pacers",
  "match_date": "2025-06-23T00:00:00", "competition": "NBA",
  "home_win": 58.2, "away_win": 41.8,
  "expected_points_home": 112.0, "expected_points_away": 111.2,
  "expected_total_points": 223.3,
  "total_points_markets": [
    {"line": 215.5, "prob_over": 75.3, "prob_under": 24.7, "model_used": true},
    {"line": 225.5, "prob_over": 48.3, "prob_under": 51.7, "model_used": true},
    {"line": 235.5, "prob_over": 26.2, "prob_under": 73.8, "model_used": true}
  ],
  "confidence": 16.4, "confidence_label": "Low",
  "model_version": "20260928T111010Z", "winner_model_used": true,
  "generated_at": "2026-09-28T11:13:57Z"
}
```

There is **no `draw` field** — basketball has no draws (zero ties in 4,149
ingested NBA games), so `home_win` and `away_win` sum to 100 by themselves.
There are no goal, half-time, corner or card markets either: those stats
don't exist in this sport, which is a different thing from a football
competition that merely lacks the data for them, and is why they're absent
rather than present-and-null. A union response model is used rather than one
schema with optional fields, so a real football value and a
not-applicable-in-this-sport value can never be confused.

`total_points_markets` follows the same per-line contract as the football
markets, with one difference: there is no Poisson fallback for basketball,
so an untrained line reports `prob_over: null` / `model_used: false` rather
than degrading to a baseline. Lines come from
`ml.prediction.predict_basketball.TOTAL_POINTS_LINES`.

Basketball predictions are served and cached but **not persisted** to
`predictions`/`prediction_history` — see docs/architecture.md's
"Multi-sport schema" for why.

### Tennis responses

A third shape, again discriminated by `sport`:

```json
{
  "match_id": 79000, "sport": "tennis",
  "home_player": "Sinner J.", "away_player": "Alcaraz C.",
  "match_date": "2025-11-16T00:00:00", "competition": "ATP",
  "surface": "Hard", "best_of": 3,
  "home_win": 72.9, "away_win": 27.1,
  "elo_home": 2193.1, "elo_away": 2126.3,
  "elo_surface_home": 2163.4, "elo_surface_away": 1984.0,
  "expected_total_games": 22.3,
  "total_games_markets": [
    {"line": 19.5, "prob_over": 61.0, "prob_under": 39.0, "model_used": true},
    {"line": 21.5, "prob_over": 43.9, "prob_under": 56.1, "model_used": true},
    {"line": 23.5, "prob_over": 32.5, "prob_under": 67.5, "model_used": true}
  ],
  "confidence": 45.9, "confidence_label": "Medium",
  "model_version": "20260928T114616Z", "winner_model_used": true,
  "generated_at": "2026-11-16T09:00:00Z"
}
```

`home_player`/`away_player` are **not** a venue: tennis sources record a
winner and a loser rather than player 1 and 2, so the slots are assigned at
ingest by a deterministic hash to stop the label leaking (see
docs/architecture.md's "Tennis"). No home advantage is applied anywhere, and
every tennis row is stored `neutral_venue=true`.

Both an overall and a **per-surface** Elo are returned, because they can
differ sharply for the same player — the example above shows an away player
rated 2126 overall but 1984 on this match's surface. `best_of` is included
because it materially changes the total-games market.

Like basketball, tennis predictions are served and cached but not persisted.

## `GET /team/{team}`

Team name is normalized (`app/utils/team_names.py`), so `man utd` and
`Manchester United` resolve to the same team. 404 if unknown.

```json
{
  "team": {"id": 1, "name": "Arsenal", "league": "English Premier League", "elo_rating": 1612.4},
  "form_last5": {"matches_played": 5, "wins": 3, "draws": 1, "losses": 1, "points_per_game": 2.0,
    "over_1_5": 4, "over_2_5": 3, "over_3_5": 1, "btts": 3, "..."},
  "form_last10": {"...": "..."},
  "recent_matches": [{"match_id": 40, "match_date": "...", "competition": "...", "home_team": "...", "away_team": "...",
    "home_score": 2, "away_score": 1, "home_ht_score": 1, "away_ht_score": 0}],
  "season_stats": {
    "season": "2025-2026", "matches_played": 12,
    "shots": {"value": 14.2, "sample_size": 12}, "shots_on_target": {"value": 5.1, "sample_size": 12},
    "corners": {"value": 6.4, "sample_size": 10}, "cards": {"value": 1.8, "sample_size": 12},
    "possession": {"value": 58.0, "sample_size": 3}, "offsides": {"value": 1.7, "sample_size": 3},
    "fouls": {"value": 9.5, "sample_size": 3}
  }
}
```

`over_1_5`/`over_2_5`/`over_3_5`/`btts` are display-only counts (out of
`matches_played`) for the match page's Form tab — see
`ml.feature_engineering.features.compute_goal_rate_form`. Nothing in
`TeamFormSummary` is read by a training pipeline; that's `TeamForm`
(`compute_team_form`), a separate type entirely.

`recent_matches[].home_ht_score`/`away_ht_score` are `null` wherever the
source never recorded a half-time score (see docs/architecture.md's
"Half-time goals" section) — never a fabricated 0-0. The match page's
Recent Matches tab uses these for its Full Time / Half Time toggle, which
recomputes each row's W/D/L result from whichever score is selected, not
just the printed number.

`season_stats` is `null` for a team with no completed match history at all.
"Current season" is whichever season the team's most recent completed match
falls in — matches from any other season are excluded, not blended in. Each
stat's `sample_size` is how many of that season's matches actually reported
it, independent of `matches_played`: `possession`/`offsides`/`fouls` only
exist from the point `scripts/fetch_match_stats.py` started running, so a
team can have a full season of `shots`/`corners` (long-ingested historical
columns) alongside a `sample_size` of 2 or 3 for those three. `value` is
`null` when `sample_size` is 0 — never a fabricated 0.0. There is no
`expected_goals` or `total_passes` row here (both real fields on the
reference site this was modelled on) — this engine has no recorded xG
independent of its own predictions, and no passes data at all; inventing
either would blur a prediction with a fact, or show a stat from nowhere.

## `GET /elo/{team}`

Current rating plus the full match-by-match Elo history. 404 if unknown.

## `GET /history/{match_id}`

The prediction timeline for a match — every snapshot ever computed for it, in
chronological order, so you can see how the prediction moved as new data came
in. 404 if the match doesn't exist (an empty `timeline` is valid if
`/predict` was never called for it).

## `POST /retrain`

Triggers a synchronous training run of the XGBoost match-result model on the
current `data/processed/matches.csv`. Returns the new model's metrics, or
`400`/`500` (with the failure logged to `training_runs`, status="failed") if
training couldn't complete (e.g. not enough data). To retrain the O/U or
BTTS models, run `uv run python -m ml.training.train_over_under` /
`train_btts` directly (or wait for the weekly scheduler job — see
`app/scheduler.py`) — this endpoint covers the primary match-result model.

## `GET /model/performance`

Query params: `model_name` (default `xgboost_match_result`, also accepts
`lightgbm_over_under_2_5` or `gbm_btts`), `limit` (default 10, max 100).
Returns the currently active version plus recent version history with their
stored metrics (accuracy, log-loss, sample counts).

## `GET /value/{match_id}`

Compares the model's probability against the bookmaker-implied probability
(overround-adjusted) for each outcome. `404` if the match doesn't exist or
has no bookmaker odds ingested (only completed historical matches from
Football-Data.co.uk currently carry odds — live fixtures won't until an odds
feed is ingested for them).

```json
{
  "match_id": 42, "home_team": "Arsenal", "away_team": "Chelsea",
  "odds_home_win": 2.0, "odds_draw": 3.4, "odds_away_win": 3.8,
  "edges": [
    {"outcome": "home_win", "model_probability": 54.2, "market_implied_probability": 48.1, "edge": 6.1},
    "... draw, away_win, sorted by |edge| descending"
  ],
  "disclaimer": "Mathematical difference... Not a profit guarantee."
}
```

## `GET /model/monitoring`

Query params: `model_name` (default `xgboost_match_result`). Backfills any
newly-completed matches' actual results onto `prediction_history`, then
returns a calibration report (Brier score, overall accuracy, reliability
buckets), a metric-drift status (accuracy/log-loss vs. the previous training
run), and a feature-drift status (each feature's mean vs. the previous
training run, independent of whether accuracy moved).

```json
{
  "calibration": {"num_predictions": 340, "brier_score": 0.61, "overall_accuracy": 48.2,
    "buckets": [{"bucket_low": 40.0, "bucket_high": 50.0, "count": 120, "mean_predicted_probability": 44.8, "actual_accuracy": 46.7}]},
  "drift": {"model_name": "xgboost_match_result", "has_enough_history": true,
    "latest_accuracy": 0.4956, "previous_accuracy": 0.51, "accuracy_delta": -0.0144,
    "drift_detected": false, "reasons": ["No significant drift detected."]},
  "feature_drift": {"model_name": "xgboost_match_result", "has_enough_history": true,
    "shifted_features": [], "drift_detected": false,
    "reasons": ["No significant feature drift detected."]}
}
```

## `GET /standings/{competition}`

Live league table, computed from our own ingested match results (no
external data source). Query params: `season` (defaults to the most recent
season with completed matches). `404` if the competition has no completed
matches (or none for the given `season`).

```json
{
  "competition": "English Premier League", "season": "2024-2025",
  "table": [
    {"team": "Liverpool", "played": 38, "won": 25, "drawn": 9, "lost": 4,
     "goals_for": 86, "goals_against": 41, "goal_difference": 45, "points": 84},
    "... rest of the table, sorted by points, then goal difference, then goals for"
  ]
}
```

## `GET /injuries/{team}`

Current injuries/suspensions, as last synced from API-Football
(`scripts/sync_injuries.py`, requires `API_FOOTBALL_KEY`). `404` if the team
doesn't exist; if the team exists but has never been synced, returns `200`
with `available: false` and a message explaining how to sync it — never a
guess.

```json
{
  "team": "Arsenal", "available": true, "synced_at": "2026-09-22T15:30:00",
  "injuries": [{"player_name": "Bukayo Saka", "injury_type": "Injury", "reason": "Hamstring", "fixture_date": "2026-09-27T15:00:00"}]
}
```

## `GET /model/roi-backtest`

Retrospective flat-staking simulation: for every match in the active
model's genuinely held-out test period (never matches it trained on — see
`ml/monitoring/roi_backtest.py`) with bookmaker odds attached, stakes
`stake` on every outcome where the model's edge over the market exceeded
`edge_threshold` percentage points, and reports the result. Query params:
`edge_threshold` (default 5.0), `stake` (default 1.0). **Not a profit
guarantee** — a retrospective number on one dataset, not evidence of future
performance (see the response's own `disclaimer` field).

**Slow the first time** — live-measured at ~2 minutes against the current
dataset (it recomputes a full ensemble prediction for every held-out
match). Results are cached per `(edge_threshold, stake)` for an hour, so
repeat calls with the same params are near-instant; the dashboard exposes
this as an explicit "Run ROI backtest" button rather than auto-loading it
for exactly this reason.

```json
{
  "edge_threshold": 5.0, "stake_per_bet": 1.0,
  "num_matches_considered": 231, "num_bets": 154, "num_wins": 59,
  "total_staked": 154.0, "total_returned": 143.62, "profit": -10.38,
  "roi_percent": -6.74, "hit_rate_percent": 38.3,
  "bets": [{"match_id": 910, "outcome": "draw", "edge": 16.5, "odds": 6.33, "stake": 1.0, "won": true, "profit": 5.33}],
  "disclaimer": "A retrospective simulation... Not a profit guarantee."
}
```

## `POST /analyst/{match_id}`

The AI analyst agent's narrative for a match — Claude, calling the tools in
`app/agents/tools.py` (all backed by real data; `get_injuries`/`get_standings`
honestly report unavailability rather than guessing). `404` if the match
doesn't exist; `503` if `ANTHROPIC_API_KEY` isn't configured.

```json
{
  "match_id": 42,
  "analysis": "Arsenal have won 4 of their last 5 home games (2.4 pts/game)...",
  "tool_calls": [{"tool": "get_model_prediction", "input": {"match_id": 42}, "result": {"...": "..."}}],
  "model": "claude-sonnet-5"
}
```
