# Roadmap — what's been built, and what's still open

Every item from the original spec is now done: all model families, SHAP,
value detection, calibration/metric/feature drift monitoring, live
standings, ROI backtesting, injuries ingestion, an AI analyst agent, a RAG
knowledge base (original + real Wikipedia content), scheduled automation,
and a dashboard UI — plus the markets, leagues and adapters added after it.
The two items that once needed a project-owner decision (a real
`API_FOOTBALL_KEY` for injuries, and third-party knowledge-base licensing)
were both resolved; their sections below record how.

**What's genuinely still open**, each called out in context further down.
Ordered by what blocks the most.

### Resolved

- **Nothing fetched results for fixtures predicted forward — fixed.**
  `scripts/fetch_results.py` closes the loop `fetch_upcoming_fixtures.py`
  opened: one request per date at API-Football's `/fixtures` endpoint,
  matched back to our row by fixture id (`external_id="apif-{id}"`, so no
  fuzzy team-name matching), filling in the final score and flipping
  `status` to `"completed"`. Rebuilds Elo history when anything changed.
  Wired into the scheduler every 3 hours, ahead of the existing 6-hourly
  `evaluate_predictions_job`.

  Run once against the real database: 29 fixtures went from scheduled to
  completed, and the effect was immediate — the live record (see below)
  started reading 24/29 (82.8%) the moment it ran, the backtest-only
  caveat disappeared from the home and progress pages, and the board's
  "Yesterday" section graded for the first time. This was the highest-value
  single fix in the repo, and it now runs on its own.

  One real constraint it surfaced: a free API-Football plan only serves a
  ~3-day rolling window, so `--days` defaults to 3 rather than wasting
  requests on dates a free key can never answer. A paid plan can pass a
  wider `--days` for a deeper backfill. Corners/cards are not fetched —
  that needs a second request per fixture and several competitions record
  neither stat anyway (a corners call on those already resolves VOID) —
  which is a deliberate scope decision, not an oversight.

- **The track record was entirely backtested — now has a live component.**
  All 807 predictions stored *before* this fix were generated after the
  match from history truncated at kick-off. `/progress` has always reported
  live and backtested records separately; `fetch_results.py` is what lets
  the live side actually receive completed matches, and it now does. It
  will keep growing day over day rather than needing anything further.

- **A concurrent write could wipe every pick off the board — fixed.** Reported
  directly: a graded day's board showed real scores and odds but a dash in
  every pick column. Traced to `predict_for_matches` sharing one SQLAlchemy
  session across a whole day's fixtures — when a concurrent writer (originally
  found via `fetch_odds.py`'s backfill pass, but any concurrent DB write
  would do it) held SQLite's single write lock, the first fixture's failed
  statement left that shared session unable to run another one, cascading
  "one bad fixture" into "every fixture after it in the same batch has no
  pick" without ever showing an error. Fixed by rolling back the session the
  moment a fixture (or a whole day's shared setup) fails, so the promise the
  code already documented — "a fixture the engine cannot price yields None
  rather than failing the batch" — is actually true instead of only true
  until the first lock contention.

- **`fetch_odds.py`'s bulk pass alone left real gaps — patched.** Its
  `/odds?date=` call paginates every fixture API-Football knows about that
  day, and a free plan caps that pagination at 3 pages; our own modelled
  fixtures don't always land in the first 3, and once a match kicks off
  there's no going back to price it from that endpoint. Confirmed directly
  against the API that `/odds?fixture={id}` is not paginated and does return
  prices for fixtures the bulk pass missed, so a per-fixture fallback now
  runs after it, scoped to `apif-`-sourced fixtures still missing a price,
  capped by `--max-backfill`, and resilient to the free plan's per-minute
  rate limit (a 429 stops the run cleanly rather than crashing it, leaving
  the rest for the next scheduled run).

- **Supabase URL + anon key.** Blocks everything auth-shaped: sign-in, user
  accounts, the Hit&Win prediction game, and subscription gating.
- **Bookmaker links.** Asked several times, never answered. A "Bet now
  @1.95" button is an affiliate referral and carries licensing and
  age-gating obligations. Until it is answered, odds stay informational and
  nothing links out.

### Known defects, measured and unfixed

- **The confidence score does not discriminate.** Over 851 stored
  predictions it runs 78.5–99.4, median 94.4, sd 3.6 — the top fifth of its
  own nominal 0–100 scale. A "bankers above 8/10" filter admitted 29 of 29
  fixtures on a real card, which is why `/bankers` selects on probability
  instead. The metric is an estimator-agreement measure and the estimators
  agree almost always; it wants rescaling or replacing, and that is a
  deliberate change to a documented formula rather than a tweak.
- **International predictions are data-starved.** Our international history
  starts 2022. Morocco has 28 completed matches, Lesotho 17, Gambia 13, and
  on those fixtures all three estimators agree with each other and disagree
  with the market together. Elo weighting and Poisson pooling took the
  calibration gap from 14.0 to 3.8 points, but the rest is volume:
  ingesting pre-2022 internationals would roughly 4x the pool and is the
  single highest-value data job.
- **`Andorra` is one team row for two entities** — FC Andorra (84 Spanish
  Segunda matches) and the Andorra national team (20 internationals) share
  one Elo of 1317.5, which describes neither. Fixing it means splitting the
  row and reassigning matches, which changes historical records, so it is
  left for a decision.
- **Curaçao is stored with a literal U+FFFD replacement character**
  (`Cura�ao`). Something still reaches the DB mis-decoded — likely
  `fetch_international.py` rather than the `clean_data` path that was fixed.
- **Thin-data fixtures still print large expected-value figures** ("+1344.0%
  expected value" on Lesotho v Morocco). Flagged `THIN DATA` with an
  explanatory sentence, but it is still the largest number on the panel.
  Suppressing the percentage entirely when evidence is thin is a one-line
  change awaiting a call.

### Pre-existing

- **Re-run the ROI backtest against the current models.** The -6.74% figure
  in "ROI backtesting" was computed on the old single-league dataset and is
  now only a historical result.
- **Per-league models, if per-league accuracy matters more than one unified
  model.** See "League expansion, 5 → 16 leagues" — a real architecture
  change (18x the model registry and retraining surface), not a tuning
  tweak, so it's a deliberate decision rather than an obvious next step.
- **Scraping non-Wikipedia sources for the knowledge base**, which is a
  per-source licensing decision — see "Real third-party knowledge base
  content" and `rag/README.md`.

Everything below this line is the record of what was built, newest last.

## Live injuries ingestion — done, live-verified

`scripts/sync_injuries.py` syncs real injury/suspension data from
API-Football (api-sports.io) — requires your own `API_FOOTBALL_KEY` (a free
tier exists; sign up at dashboard.api-football.com). It resolves and caches
each team's API-Football ID by name search, fetches current injuries for the
auto-detected current season, and replaces that team's stored rows.

This was originally built against the v3 API shape corroborated from public
searches (the official docs block automated fetches from this environment)
and then genuinely tested once a real key was provided — two real bugs
turned up against the live response and were fixed:
- `player.name` can be present-but-`null` in a real entry, which a bare
  `.get("name")` doesn't catch (it's not a missing key); now checked as a
  value, with a regression test.
- `team`+`season` returns one row per missed *fixture*, not one row per
  player — a season-long injury produced 200+ rows for a 25-man squad.
  `sync_team_injuries` now keeps only each player's single most-recent
  entry. The hardcoded default season (`2025`) had also gone stale by the
  time this shipped; it's now auto-detected from today's date.

Verified live end-to-end: synced Arsenal, got 7 sensible current entries
(down from 216 before the fix), correctly served by `GET /injuries/{team}`
and consumed by the AI analyst agent in a real tool-calling run.

`get_standings` was already done in the previous pass —
`app/services/standings_service.py`, computed live from our own ingested
match results, no external source needed.

## AI analyst agent — live-verified

Ran `POST /analyst/{match_id}` for real for the first time with a live
`ANTHROPIC_API_KEY`. Along the way found and fixed a real bug: the agent
read `ANTHROPIC_API_KEY`/`ANALYST_MODEL` via raw `os.environ.get(...)`, but
pydantic-settings loads `.env` values into the `Settings` model without
exporting them to the process environment — so a key that only existed in
`.env` (never in the actual shell environment) was invisible to that code
path, even though every *other* credential in this codebase correctly goes
through `Settings`. Fixed by adding `anthropic_api_key`/`analyst_model` to
`Settings` and reading through `get_settings()` like everything else;
`tests/test_analyst.py` now specifically regression-tests "a key present
only via `Settings`, absent from `os.environ`, must still work."

The live response (Southampton vs Arsenal) correctly called
`get_model_prediction` and `get_team_form` for both teams, then cited real
numbers from those results (82.8% win probability, Elo 1724 vs 1243.7, form
records) with no fabricated statistics.

## Real third-party knowledge base content — done

`rag/knowledge_base/wikipedia/*.md` now holds real Wikipedia articles
(Expected goals, Elo rating system, Poisson distribution, Home advantage,
Brier score, Sports betting) — CC BY-SA 4.0, legitimately reusable with
attribution, fetched and attributed automatically by
`rag/ingestion/fetch_wikipedia.py`. This sits alongside (doesn't replace)
the original reference articles in `rag/knowledge_base/*.md`. Verified live:
74 total indexed chunks, real semantic search returns the correct real
content (e.g. a Brier-score query returns the real Wikipedia Brier score
passage). Scraping other, non-Wikipedia sites remains a per-source licensing
decision left to the project owner — `rag/README.md` covers how to add more.

## ROI backtesting — done

`ml/monitoring/roi_backtest.py` simulates flat-staking every value edge
above a threshold, restricted to the same held-out test-period matches the
active models' own reported accuracy/log-loss come from (re-derived via
`resolve_test_period_start`, so this never backtests on data a model
trained on — that would be look-ahead bias and make the number meaningless).
Exposed as `GET /model/roi-backtest?edge_threshold=&stake=`. Real result on
the current EPL 2022-25 dataset at a 5-point edge threshold: 154 bets,
38.3% hit rate, **-6.74% ROI** — a real, unfavorable number, reported
honestly rather than cherry-picked, which is exactly what an early-stage
model with ~50% 3-way accuracy should produce against efficient bookmaker
odds. Worth re-running once more seasons/leagues are ingested.

## Feature drift detection — done

`ml.monitoring.drift.check_feature_drift` compares each feature's mean
between the two most recent training runs' `feature_summary` (mean/std per
feature, computed by `ml.training.common.compute_feature_summary` and stored
in `training_runs.metrics` at training time), flagging anything that moved
more than 0.5 standard deviations — independent of whether accuracy/log-loss
moved. Surfaced in `GET /model/monitoring` alongside the existing
metric-drift check.

## Frontend / dashboard UI — done, live-verified in a real browser

`app/static/dashboard/` — plain HTML/CSS/vanilla-JS, no build step, served
by FastAPI itself at `/dashboard`. Covers matches (browse/filter → full
prediction with SHAP explanation, value vs. odds, prediction timeline, and
a working "Ask the analyst" button), standings, team lookup (Elo history
chart, form, recent matches, injuries), and model monitoring (performance,
calibration scatter, drift, ROI backtest).

Two new endpoints support it — `GET /matches` and `GET /competitions`
(`app/api/routes_matches.py`) — since nothing else let a caller discover a
`match_id` from scratch.

Tested end-to-end in a real Chrome session, not just unit tests: real
predictions rendering correctly, the Elo history line chart (1513→1724
over 114 real matches), the real 2024-25 EPL standings table, and a live
`POST /analyst/{match_id}` call through the UI that correctly cited real
synced injury data (Arsenal's absentees) and correctly said Southampton's
injuries weren't synced — exactly the honesty behavior the backend was
built for. That session also caught one real bug: `GET /model/roi-backtest`
took ~2 minutes uncached, which silently blocked the whole Monitoring page
when fetched alongside the fast panels. Fixed with a server-side cache
(`app/api/routes_roi.py`, 1-hour TTL) and by making the dashboard's ROI
panel an explicit opt-in button instead of auto-loading — found by testing
the built thing against the real backend, not by guessing upfront.

## Multi-league retrain (5 leagues x 10 seasons) — done, live-verified

*(Superseded by the 16-league expansion further down this file — kept here
as the historical record of what the first multi-league retrain found.)*

Retrained on the full dataset the "Frontend" section above still shows as
single-league (EPL only): Premier League, La Liga, Bundesliga, Serie A,
Ligue 1, 2015-16 → 2024-25 (18,011 matches). This surfaced two real issues
a single-league dataset never could, both fixed and covered by
`tests/test_multi_league.py` (see `docs/architecture.md`'s "Multi-league
support" section for the technical detail):

- Poisson fitting is now scoped to the target match's own competition —
  without this, one shared "average" goal rate across 5 leagues with
  genuinely different scoring/home-advantage baselines would silently
  corrupt the expected-goals estimate for every league.
- A one-hot competition feature was added to `FEATURE_COLUMNS` so the ML
  models can learn league-specific patterns instead of averaging over
  incompatible ones.

Real, measured accuracy improvement from adding leagues + these two fixes
together (not just more rows): match-result 49.6% → **52.5%**, Over/Under
2.5 54.8% → **57.7%**, BTTS 51.3% → **54.3%**.

Also found and fixed two real bugs along the way, unrelated to the modeling
decisions above:
- `normalize_team_name` crashed on a NaN team name in the raw multi-league
  CSVs (`pandas.astype(str)` doesn't reliably turn a NaN float into the
  string `"nan"` for an object-dtype column) — fixed at both the pipeline
  level (`scripts/clean_data.py` now drops null-name rows *before*
  normalizing) and defensively inside `normalize_team_name` itself.
- The walk-forward feature-engineering loop was `O(n²)` — fine at
  ~1,100 EPL-only matches (~10s), but projected at ~56 minutes for 18,011
  matches, i.e. impractical to ever retrain with. Fixed with
  `TeamHistoryIndex` (`ml/feature_engineering/features.py`), a per-team,
  date-sorted index enabling `O(log k)` bisect lookups instead of a full
  dataset scan per call — measured at ~15 seconds for the same run, a
  ~200x speedup, with `tests/test_feature_engineering.py` asserting the
  indexed path returns byte-for-byte identical output to the old
  plain-list path.

Live-verified end-to-end, not just via the training scripts' own printed
metrics: real `/predict` call on a held-out La Liga fixture (Athletic
Bilbao vs Barcelona) produced a sensible, correctly-favored prediction, and
`/model/monitoring` showed all 6 competition one-hot columns present at a
sane ~20% distribution each, metric drift correctly *not* flagged (accuracy
improved, not regressed), and feature drift correctly flagged a real,
explainable head-to-head feature shift from the added leagues.

The ROI backtest number in the section above (-6.74%) predates this retrain
and was computed on the old single-league dataset — it's still an accurate
historical result, but per that section's own note it's worth re-running
against the new multi-league models before quoting it as current.

## League expansion, 5 → 16 leagues — done, live-verified

The 5-league retrain above still left every other league behind a generic
fallback: `predict_match(competition=None)` blends all history into one
unscoped Poisson fit, and an unrecognized competition one-hot-encodes as
all-zero, so those matches got Elo+Poisson only, no league-specific ML
signal. To make "the model works for more than the top 5 leagues" literally
true rather than just "doesn't crash for them," expanded to every league
Football-Data.co.uk publishes in the same per-season CSV format: the big-5
top flights' second divisions (English Championship, 2. Bundesliga, Serie
B, Segunda División, Ligue 2) plus six more top flights (Eredivisie,
Belgian Pro League, Primeira Liga, Süper Lig, Greek Super League, Scottish
Premiership) — **16 leagues total, 55,641 matches** (`scripts/download_data.py`'s
`KNOWN_LEAGUES`, `scripts/clean_data.py`'s `LEAGUE_NAMES`, and
`ml.training.common.KNOWN_COMPETITIONS` all extended together, so the
one-hot feature schema, the ingestion mapping, and the download CLI stay in
sync).

Real, honestly-reported result — this widens *coverage*, and does not
improve overall held-out accuracy: match-result **50.0%** (down from 52.5%
on the narrower 5-league set), Over/Under 2.5 **56.2%** (down from 57.7%),
BTTS **53.8%** (down from 54.3%). This is expected, not a regression to fix:
several of the added leagues (second divisions, smaller top flights with
less analytics/data coverage) are genuinely noisier and harder to predict
than the original 5, and a single shared model now has to fit all 16 rather
than excluding the hard ones. The alternative — training 16 separate
per-league models — would likely recover some of this accuracy but is a
real architecture change (16x the model registry, 16x the retraining
surface), not something to do silently as part of a "more leagues" request;
left as a possible future item if per-league accuracy matters more than one
unified model.

Verified live: `/competitions` lists all 16 leagues with real per-league
match counts and season coverage; a real `/predict` call on a completed
Turkish Süper Lig match (Samsunspor vs Kayserispor) using the new model
version returned a sensible, correctly-favored prediction with a real
elo/form-based SHAP explanation — confirming a previously-unsupported
league now gets full model treatment, not just the Elo+Poisson fallback.
`/model/monitoring` correctly showed 0.0 accuracy/log-loss drift (both
training runs happened back-to-back in this session, so "previous" and
"latest" are effectively the same run) and no feature drift.

Feature-frame construction time was re-measured at this larger scale:
**~66 seconds** for 55,641 matches (up from ~15s at 18,011) — see
`docs/architecture.md`'s "Feature-engineering performance at scale" section
for why that's still consistent with the `TeamHistoryIndex` fix holding,
not a regression of it.

139 tests still pass unchanged — `KNOWN_COMPETITIONS`-dependent tests assert
against `len(KNOWN_COMPETITIONS)` rather than a hardcoded count, so the
expansion needed no test changes.

## MLS + Saudi Pro League, 16 → 18 leagues — done, live-verified

Asked directly for MLS and the Saudi Pro League specifically. Checked both
against our existing source rather than assuming either would just work
with `download_data.py`:

- **MLS** *is* on Football-Data.co.uk, but published differently from every
  other league here — one all-seasons-in-one file per country, different
  column names, no shots/corners/cards. `download_data.py` would silently
  skip it (missing required columns). New adapter script
  `scripts/fetch_extra_league.py` downloads that file, remaps its columns
  onto the standard shape, and writes it out as normal per-season CSVs.
- **Saudi Pro League is not on Football-Data.co.uk at all** — checked
  directly against their published country list, not inferred from absence
  in our own config. Sourced from API-Football instead (league id 307,
  confirmed real fixture data for seasons 2016-2025) via a second new
  script, `scripts/fetch_api_football_league.py`. This needs a paid-tier
  `API_FOOTBALL_KEY` (confirmed with the project owner before building
  this) — the free tier's daily quota can't cover ~10 seasons of
  `/fixtures` calls; one request per season (not per fixture) keeps it
  cheap even so.

Both adapters write into `data/raw/` in the exact same shape
`download_data.py` produces, so `clean_data.py`/`load_to_db.py` and the
Poisson-scoping/one-hot fixes from the section above needed zero changes to
pick them up — see `docs/architecture.md`'s "Non-native data sources"
section for the full technical detail, including what's deliberately *not*
pulled from API-Football (shots/corners/cards, odds) and why.

Dataset grew to **18 leagues, 62,568 matches** (55,641 + 4,445 MLS + 2,482
Saudi). Retrained all three models: match-result **50.0%** (essentially
unchanged from the 16-league 50.0%), Over/Under 2.5 **56.2%** (unchanged
from 56.2%), BTTS **54.7%** (up slightly from 53.8%) — adding two
leagues that are each under 5% of the combined dataset barely moves overall
accuracy either way, as expected.

Live-verified real per-league treatment, not just successful ingestion: a
real `/predict` call on a completed Saudi Pro League match (Al-Hazm vs Al
Taawon) and a completed MLS match (Inter Miami vs Vancouver Whitecaps) each
returned a sensible, correctly-favored prediction, and each one's SHAP
explanation correctly surfaced that match's own one-hot competition feature
(`competition_saudi_pro_league`, `competition_major_league_soccer`) among
its top contributors — confirming the league-specific ML signal genuinely
extends to both new leagues, not just Elo+Poisson. `/competitions` lists
all 18 leagues with real match counts. 139 tests still pass; `black`/`ruff`
clean.

## Daily ingestion scheduling + 3 more leagues, 18 → 21 leagues — done, live-verified

Asked directly for the board to have fixtures every day, like the reference
site, which the owner explicitly acknowledged would mean covering more
leagues. Investigated before building: checked the live API-Football
response for the days around the request (2026-09-30 / 10-01) and found
almost no top-flight football anywhere in the world that week — a genuine
FIFA international break, not a gap in this engine's coverage. League
breadth cannot fix a week where the leagues themselves aren't playing; the
two things that *can* be fixed were the actual target of this pass.

**Nothing ever scheduled fixture or odds ingestion.** `fetch_results.py`
(above) was wired into the scheduler; `fetch_upcoming_fixtures.py` and
`fetch_odds.py` never were — the board only ever reflected whatever someone
last ran by hand. Both are now scheduled every 4 hours (odds 15 minutes
after fixtures, so newly-ingested rows already exist to price). Found and
fixed a real bug while wiring this in: both scripts called
`argparse.parse_args()` with no explicit argument list, which reads the
*host process's actual* `sys.argv` — harmless from a standalone CLI call,
but would have broken or silently misbehaved the moment either ran as a
scheduled job inside the live server. Both now take an optional `argv`
parameter and the scheduler jobs pass `[]` explicitly.

**Three more leagues**, chosen for immediate relevance (all mid-season right
now, unlike the European calendar during this international break):
**Argentine Primera División** (API-Football id 128), **Brazilian Série A**
(id 71), **Japanese J1 League** (id 98). Sourced via the existing
`scripts/fetch_extra_league.py` adapter, the same one built for MLS.

Found and fixed two real bugs in that script while pulling real data through
it for the first time since MLS:
- **Silent whitespace mismatch.** Argentina's and Japan's source files carry
  the same competition name with and without a trailing space (`"Liga
  Profesional"` / `"Liga Profesional "`) — an exact-match filter was
  silently dropping 39% of Argentina's rows and 49% of Japan's. Fixed by
  stripping both sides before comparing.
- **Silent dtype mismatch.** The Season column is `int64` for some countries
  (Brazil) and a string dtype for others (Argentina) — comparing it to a
  Python `int` matched everything for Brazil and nothing at all for
  Argentina. Fixed by comparing both sides as strings.

Neither bug threw an error; both would have shipped as "successfully"
downloaded files missing most of their data. Caught by inspecting row counts
before trusting the pipeline, not by a test — there wasn't one for this
script, and this is exactly the kind of silent-corruption risk that argues
for adding one before the next country goes through it.

Registered all three in every place a competition needs registering:
`scripts/clean_data.LEAGUE_NAMES`, `ml.training.common.KNOWN_COMPETITIONS`,
`ml.competition_catalogue`, and `fetch_upcoming_fixtures.LEAGUE_ID_TO_COMPETITION`.
Downloaded 2019-2025 (2021-2025 for Argentina, whose earlier seasons use a
split-year format this pipeline doesn't model), loaded **7,073 new matches**
(dataset now **71,366 football matches, 21 leagues**), rebuilt Elo across
151,483 completed matches spanning all sports.

Retrained every model. Match-result **49.6%** and BTTS **54.5%** (both
essentially unchanged from pre-expansion, as expected — three leagues
totalling under 10% of the dataset barely move overall accuracy). One test
had to be updated: it used "Brazilian Serie A" as its example of an
*unmodelled* competition, which broke the moment that stopped being true.

Live-verified with a real `/predict` call on a completed Brazilian Serie A
match (Ceará vs Palmeiras): returned a sensible, correctly-favored
prediction (47.7% Palmeiras) using the freshly-trained model version, with
goals markets available and corners/cards correctly reporting unavailable
(this source carries no shot/corner/card columns for these countries, same
as MLS and the Saudi Pro League). `/competitions` lists all 21 football
leagues. 361 tests pass; `black`/`ruff` clean.

**Not done in this pass, and why:** 12 more Football-Data.co.uk "extra"
countries are available through the same adapter (Austria, China, Denmark,
Finland, Ireland, Mexico, Norway, Poland, Romania, Russia, Sweden,
Switzerland) — left for a deliberate next batch rather than added
speculatively, since each one needs the same registration, retrain, and
live-verification, and picking countries whose season is genuinely live
right now is time-sensitive information rather than a one-off decision.

## Corners feature + Corners/Cards markets — done, live-verified

*(The single-line design below was superseded by multi-line markets
immediately after — see "Corners/Cards multi-line markets" further down —
kept here as the historical record of the first pass.)*

Corners and cards had been ingested (`app/models/match.py`) since Phase 1
but never used for anything. Asked directly to add corners to training,
and "possibly other markets" — scoped via two questions: corners as both a
feature *and* a new market (not one or the other), plus cards as a second
new market in the same pass.

- **Feature.** `ml.feature_engineering.features.compute_corner_form` adds
  rolling per-team corners-won/conceded averages to `FEATURE_COLUMNS` — the
  existing match-result/O-U/BTTS models get this signal too, not just the
  two new markets. Matches missing corner data (not every league/season has
  it) are skipped from the rolling average, not zero-filled — the same
  defensive pattern as the NaN-team-name fix from the earlier multi-league
  retrain, applied to a new column.
- **Two new markets.** Corners Over/Under 9.5 and Cards Over/Under 4.5 —
  both real bookmaker lines, checked against our own data rather than
  guessed (51.0% and 44.4% over respectively, close to balanced). Each
  reuses `PoissonModel` exactly as-is for a real statistical baseline
  (corners/cards are non-negative count stats with the same "team strength"
  structure as goals — legitimate reuse, not a hack), blended with a new
  dedicated model (`ml.training.train_corners` — LightGBM, `ml.training.train_cards`
  — Gradient Boosting) the same way Over/Under-goals and BTTS already work.
- **Honest unavailability.** MLS and the Saudi Pro League have zero
  corner/card data (see the two sections above); several other leagues are
  partially covered (~77-82%) rather than 100%. When a competition has no
  data for a stat at all, both markets come back `null`/"N/A" end-to-end —
  API, dashboard, `*_model_used` flags — rather than a number computed from
  an all-zero-filled feature vector that would look real but carry no
  signal. See `docs/architecture.md`'s "Corners and cards" section for the
  full technical detail.

Retrained all five models on the full 18-league/62,568-match dataset (all
three existing ones needed retraining too, since `FEATURE_COLUMNS` changed
shape): match-result 50.1%, Over/Under 2.5 goals 56.5%, BTTS 54.8%, Corners
9.5 **54.7%**, Cards 4.5 **59.8%** — both new markets meaningfully beat a
naive 51%/44% base-rate guess.

Live-verified: a real `/predict` call on a completed EPL match (Wolves vs
Brentford) returned real corners/cards probabilities with `corners_won`/
`corners_conceded` features correctly appearing in the SHAP explanation,
while the same call on a Saudi Pro League match correctly returned `null`
for both new markets — and a bug in that exact scenario was caught and
fixed before shipping: `corners_model_used`/`cards_model_used` initially
reported `true` even when the market itself was `null` (the model artifact
was loaded, just never actually used because there was no Poisson baseline
to blend it with) — fixed to require both. 9 new tests
(`tests/test_corners_and_cards.py` plus additions to
`tests/test_feature_engineering.py`/`tests/test_api_predict.py`), 148
total passing; `black`/`ruff` clean. Also wired into `app/scheduler.py`'s
weekly retrain job and the dashboard's model-monitoring panel, so the two
new models get the same automation/observability as the original three.

## Corners/Cards multi-line markets — done, live-verified

Asked directly for more lines: corners at 7.5/8.5/9.5, cards "from 2.5 up."
The cards upper bound was genuinely ambiguous as asked — clarified via a
question, landing on 2.5/3.5/4.5 (matching corners' 3-line pattern).

This wasn't just "add more thresholds" — it meant re-architecting how the
markets are represented, since the single-line design above assumed
exactly one number per market end-to-end (API field, DB column, dashboard
tile):

- **Each line is its own genuine market**, so each gets its own trained
  classifier — `ml.training.train_corners`/`train_cards` took a `--line`
  argument instead of a fixed constant, and each line registers under its
  own model name (`model_name_for_line`, e.g.
  `lightgbm_over_under_corners_8_5`). 9 models total now (3 fixed +
  3 corners lines + 3 cards lines), up from 5.
- **The Poisson baseline is different: one fit per stat, reused across
  every line.** `prob_over_under(line=...)` is a real calculation off the
  same fitted scoreline matrix regardless of which line is asked for, so
  fitting `PoissonModel` three times per stat would've been wasted work —
  `ml.prediction.predict._fit_count_stat_poisson` fits once,
  `_build_market_lines` calls `prob_over_under` once per line against that
  one fit.
- **API/DB shape changed from 4 scalar fields to 2 lists.**
  `corners_over`/`corners_under`/`cards_over`/`cards_under` (plus their
  `*_model_used` flags) became `corners_markets`/`cards_markets`, each a
  list of `{line, prob_over, prob_under, model_used}`. The DB followed the
  same shape: the 4 `prob_corners_*`/`prob_cards_*` Float columns added for
  the single-line design were dropped in favor of 2 JSON columns
  (`corners_markets`/`cards_markets`) on both `predictions` and
  `prediction_history` — a fixed-columns-per-line schema doesn't scale if
  the line set ever changes again, a JSON list does. One real migration
  issue caught before shipping: autogenerate produced a `NOT NULL` JSON
  column with no default against a table that already had rows (from
  earlier live-verification predictions) — fixed to `nullable=True` by
  hand before applying it.
- **Dashboard** replaced the fixed 4-tile grid with a small table per
  market (one row per line), and the model-monitoring panel's tracked
  model list grew from 5 to 9 names.

Retrained the 6 new per-line models on the full 18-league/62,568-match
dataset (the 3 fixed models didn't need retraining — `FEATURE_COLUMNS`
didn't change, only how many lines consume it):

| Market | 7.5 / 2.5 | 8.5 / 3.5 | 9.5 / 4.5 |
|---|---|---|---|
| Corners | 73.96% | 62.86% | 54.67% |
| Cards | 78.44% | 63.78% | 59.83% |

The outer lines score meaningfully higher raw accuracy than the center
ones — expected, not a tuning win: a line further from the true 50/50
split is an easier binary classification (more of the data sits
unambiguously on one side of it), the same reason the original 9.5/4.5
lines were chosen as the "fair" bookmaker lines in the first place.

Live-verified both ends of the honesty guarantee: a real `/predict` call
on a completed EPL match returned all 3 corners lines and all 3 cards
lines with real, monotonically-decreasing probabilities (a higher line
always shows a lower P(over) — a genuine sanity check that each line is a
distinct calculation, not the same number three times) and `model_used:
true` throughout; the same call on a Saudi Pro League match correctly
returned `prob_over`/`prob_under: null` and `model_used: false` for every
line of both markets. 149 tests passing (test file rewritten for the list
shape, plus a new test asserting the three corners lines are genuinely
distinct and monotonic); `black`/`ruff` clean. `app/scheduler.py`'s weekly
retrain job updated to loop over both line lists.

## Goals multi-line + half-time goals markets — done, live-verified

Asked for more goals lines and a half-time goals market. Two things in one
pass, because the first was a precondition for the second: the goals market
had been a *single hardcoded 2.5 line* end-to-end since Phase 1 — one API
field pair (`over_2_5`/`under_2_5`), one flag
(`over_under_model_used`), one pair of DB columns — so adding any second
line meant converting goals to the same multi-line shape corners/cards
already used, and once that existed, half-time goals was a new market
slotting straight into it.

- **Goals now offers 1.5 and 2.5** (`ml.prediction.predict.GOALS_LINES`),
  each its own trained classifier (`train_over_under.py` took a required
  `--line` argument with `model_name_for_line`, matching the
  corners/cards trainers). 2.5 remains the real bookmaker center line; 1.5
  is the standard next line out.
- **Half-time goals (0.5) is a new market** (`ml/training/train_ht_goals.py`)
  with its own **independently-fitted Poisson**, not a halved full-time
  fit. Halving would have been wrong on the statistics, not just imprecise:
  teams set up differently across halves (second halves score more;
  substitutions and game state only exist in the second), so a half isn't
  "half a match". See `docs/architecture.md`'s "Half-time goals" section.
- **API/DB shape** followed the corners/cards precedent exactly:
  `over_2_5`/`under_2_5`/`over_under_model_used` became
  `goals_markets`/`ht_goals_markets`, each a list of
  `{line, prob_over, prob_under, model_used}`, and the two
  `prob_over_2_5`/`prob_under_2_5` Float columns were dropped for 2 JSON
  columns on both `predictions` and `prediction_history` (migration
  `ab73824e13f3`, deliberately `nullable=True` — existing rows from earlier
  live-verification runs have no value for them, and one of them is still
  visible as a `None`/`None` row in `predictions`).
- **Dashboard** renders both as per-line tables (`marketLinesTableHtml`,
  reused as-is from corners/cards), with an explicit "not recorded for this
  competition" note when every half-time line is `null`, and its tracked
  model list grew from 9 names to 11.

11 models total now (1 match-result + 1 BTTS + 2 goals lines + 1 half-time
goals line + 3 corners lines + 3 cards lines), up from 9. The two new ones
trained on the full 18-league/62,568-match dataset — the 9 existing models
needed no retraining, since `FEATURE_COLUMNS` didn't change, only how many
lines consume it:

| Market | Line | Accuracy | Trained on |
|---|---|---|---|
| Over/Under goals | 1.5 | **76.38%** | 62,568 matches |
| Over/Under goals | 2.5 | 56.5% (unchanged) | 62,568 matches |
| Over/Under half-time goals | 0.5 | **71.10%** | 58,053 matches |

The half-time model trains on 58,053 rather than all 62,568 matches, and
that gap is the interesting part of this pass rather than a data problem:
**market availability is per stat, not per league.** Of the 4,515 rows
without a half-time score, 4,445 are the whole of MLS — its
Football-Data.co.uk file has no `HTHG`/`HTAG` columns at all, so MLS
reports this market as unavailable — and the remaining 70 are scattered
individual gaps across 10 other leagues, which are simply dropped from
training. But the Saudi Pro League, which has *no* corner/card data,
*does* have half-time scores, because
`scripts/fetch_api_football_league.py` reads them from the same
`/fixtures` response it already reads full-time scores from.

Live-verified all three cases against a running server, which is what
actually confirmed the per-stat logic rather than a per-league assumption:

- **EPL** (Wolves vs Brentford): all 9 lines real and `model_used: true` —
  goals 1.5 → 76.7% / 2.5 → 52.2% (correctly monotonic), half-time 0.5 →
  70.9%, corners and cards likewise.
- **Saudi Pro League** (Al-Hazm vs Al Taawon): goals (76.7% / 54.3%) *and*
  half-time goals (68.4%) all real with `model_used: true`, while every
  corners and cards line correctly returned `null` / `model_used: false`.
  This is the case a per-league availability shortcut would have gotten
  wrong.
- **MLS** (Inter Miami vs Vancouver Whitecaps): goals lines real (84.4% /
  62.8%), half-time goals *and* corners/cards all correctly `null` /
  `model_used: false`.

Also confirmed the JSON columns genuinely persist to both `predictions` and
`prediction_history` (not just serialize on the way out), and that
`GET /model/monitoring?model_name=` handles the two new models cleanly —
each reports its real accuracy with "Fewer than 2 successful training runs
— nothing to compare yet" for drift, rather than erroring, which is what
the dashboard's monitoring panel needs from a first-ever training run.

Then verified in a real Chrome session against the running backend — and
that pass earned its keep by catching a bug that code inspection and the
API tests had both missed, because it existed only in the UI layer:

**The Model column claimed a Poisson number that was never computed.**
`marketLinesTableHtml` rendered `m.model_used ? "ML+Poisson" : "Poisson
only"` — a two-way branch over three real states. A line whose
`prob_over` is `null` had *nothing* computed for it: no dedicated model
*and* no Poisson baseline, since there's no data to fit one on. So every
N/A corners and cards row on the Saudi and MLS pages was labelled "Poisson
only", asserting a fallback calculation that never ran. This is the exact
misleading-flag trap the API side already had to be fixed for on
`corners_model_used` one pass earlier (see the section above), reintroduced
at the presentation layer. Fixed with a three-way `modelLabel`: "—" when
the line is genuinely unavailable, "Poisson only" reserved for its real
meaning (a Poisson number with no dedicated model for that line).

Re-checked after the fix, all three cases render correctly: the EPL match
shows all 9 lines real and "ML+Poisson"; the Saudi match shows goals and
half-time goals real while corners/cards read "N/A" + "—" under a "this
competition has no corners data" note; the MLS match shows real goals lines
with half-time goals *and* corners/cards unavailable. The monitoring page
lists all 11 active models, the two new ones dated today
(`lightgbm_over_under_1_5` 76.4%, `lightgbm_over_under_ht_goals_0_5`
71.1%). No console errors.

149 tests passing (`tests/test_api_predict.py` already asserts the list
shape and line counts for all four multi-line markets); `black`/`ruff`
clean. `app/scheduler.py`'s weekly retrain job loops over `GOALS_LINES` and
`HT_GOALS_LINES` alongside the corners/cards line lists.

## Multi-sport: international football + basketball — done; tennis blocked

Asked for international games, basketball and tennis. These turned out to be
three very different asks, and checking what was actually reachable *before*
building changed the plan — so the findings come first.

### What the feasibility check found

- **International football** is a true extension, not a new vertical. Same
  sport, same three-way outcome, same goals and half-time goals; Elo and
  Poisson both apply unchanged.
- **Basketball** is reachable on the existing api-sports key (different
  host) but is a genuinely different sport: a pulled NBA season had **zero
  draws** and a **226-point mean total**, against a football Poisson fit
  truncated at 8 goals.
- **Tennis** has no api-sports product at all (checked by DNS across their
  hosts: football, basketball, baseball, hockey, rugby, AFL, volleyball,
  handball, F1, NBA — no tennis), and the intended GitHub dataset turned out
  to be gone. It was reported blocked, then unblocked from a different
  source on a follow-up — see the "Tennis" subsection below.

The project owner chose the generalised schema (one `matches` table with a
`sport` discriminator) over per-sport tables, and confirmed non-commercial
use for the tennis licensing question.

### Foundation: multi-sport schema

Migration `c1d2e3f4a5b6`. `matches.sport`/`teams.sport` defaulting to
`"football"` so the existing 62,568 rows kept their meaning with no
backfill; `home_goals`/`away_goals` renamed to `home_score`/`away_score`
(222 occurrences across 35 files) because that column holds goals, points
and games won depending on sport; `matches.neutral_venue`; and `teams.name`
traded its global UNIQUE for `UNIQUE(sport, name)`.

Done as a real `ALTER ... RENAME` rather than add-and-drop, since those
columns hold every match ever ingested. Verified after applying: 62,568
matches and 512 teams still present, all scores intact.

Three real issues surfaced while doing it, each silent rather than loud:

- **The processed CSV went stale.** `data/processed/matches.csv` still had a
  `home_goals` header while the code had moved on, so the ROI backtest
  failed with `KeyError: 'home_score'`. Fixed by regenerating through the
  pipeline rather than shimming the old name — the pipeline is the source of
  truth, and a compatibility alias would only have hidden the next drift.
- **Elo was keyed by team name, across all sports.**
  `rebuild_elo_history` ran one engine for everything, so a football club
  and a basketball franchise sharing a name would have had their rating
  histories fused — undoing `UNIQUE(sport, name)` via a name-keyed dict.
  Now one engine per sport.
- **Prediction history wasn't scoped to a sport.** The worst of the three:
  `_all_completed_history` would have fed ~113-point basketball games into
  the football Poisson fit the moment basketball was ingested, corrupting
  every football prediction without raising anything. Now filtered by the
  target match's sport, and pinned by a test.

### International football

`scripts/fetch_international.py` — World Cup, Euros, Nations League, Copa
America, the Africa Cup of Nations (finals *and* qualifiers) and friendlies
from API-Football, one request per competition-season. **1,798 matches**
ingested (64,365 football matches total).

**AFCON** was added on a follow-up request and turned out to be the best
illustration of why the neutral-venue flag is set per *competition* rather
than per competition family. The finals (league id 6, 52 matches) are one
host nation's tournament and are flagged neutral; the **qualifiers** (league
id 36, 142 matches) are ordinary home-and-away fixtures over two years and
are deliberately not. Two halves of the same competition, opposite flags.

Its season numbering is also its own: AFCON runs on an odd-year cycle and
the 2023 edition was actually *played* in January-February 2024, which
API-Football still files under season 2023. Verified against reality rather
than assumed — the most recent ingested row is Nigeria 1-2 Ivory Coast on
2024-02-11, which is the real 2023 final. That match is also a live example
of the host-nation approximation noted above: Ivory Coast hosted, so its own
matches are marked neutral even though they were genuinely home games. Two things genuinely differ from
domestic football, and both are handled:

- **Neutral venues.** Tournament football has no real home side, so
  `matches.neutral_venue` drives `EloEngine._home_offset`, which returns
  zero — an evenly-rated pair on neutral ground is a true 50/50 rather than
  favouring whichever side the fixture list named first. Flagged per
  competition: World Cup / Euros / Copa America neutral (147 matches),
  Nations League and friendlies not, because those are genuinely
  home-and-away. Known bounded approximation: the *host* nation's own
  matches really are home games and are marked neutral anyway — erring
  toward neutral declines to credit an advantage rather than inventing one.
  The Poisson side needed no equivalent fix, since it is already fitted per
  competition, so a fully-neutral competition learns equal home/away rates
  from its own data.
- **Tournament years aren't split seasons.** `WC_2022.csv` and `E0_2324.csv`
  are both four numeric digits; `_season_label` now tells them apart by
  whether the halves are consecutive. Without this a World Cup would have
  been labelled "2020-2022".

`KNOWN_COMPETITIONS` grew 18 -> 25, which changes the one-hot feature width,
so all 11 football models were retrained. (AFCON landing mid-retrain would
have left the in-flight run building 23-competition models that were stale
on arrival, so that run was stopped and restarted once against the final
schema rather than retraining twice.)

**Season depth is capped by the API plan, not by the code.** The key is
currently on a *free* plan, which serves 2022-2024 only and rejects older
seasons with a `plan` error (the fetcher skips those rather than aborting).
The competitions themselves go back much further — World Cup to 2010, Euros
to 2008, verified against `/leagues`. A paid plan widens the season lists in
`COMPETITIONS` and nothing else changes. Note that the Saudi Pro League
section above records a paid tier being used earlier; that subscription has
since lapsed back to Free.

### Basketball

`scripts/fetch_basketball.py` — **4,149 NBA games** across 2022-23, 2023-24
and 2024-25, written straight to the DB (no `clean_data` step: that script
exists to reconcile 18 leagues of inconsistent CSV dialects, and one
consistent JSON API has none to reconcile).

Its own feature set (`ml/feature_engineering/basketball.py`), its own
trainers, and its own prediction path (`ml/prediction/predict_basketball.py`)
rather than sport conditionals threaded through the football code. It shares
what is genuinely shared: Elo, and the leakage-safe `TeamHistoryIndex`.

Results, reported against a real baseline rather than at headline accuracy:

| Model | Accuracy | Baseline | Real edge |
|---|---|---|---|
| Winner | **64.89%** | 54.12% (always home) | **+10.8pp** |
| Total 215.5 | 71.91% | 71.67% (majority class) | +0.24pp — none |
| Total 225.5 | **59.81%** | 54.72% | **+5.1pp** |
| Total 235.5 | 66.59% | 65.38% | +1.2pp |

The outer totals lines look strong on raw accuracy and are not: a line far
from 50/50 is an easier binary problem, so most of that number is base rate,
not skill. Only the centre line adds real value. This is exactly what
`majority_class_base_rate` was recorded for, and it is reported here rather
than quietly quoting 71.91%.

Live-verified end to end on a real fixture — Game 7 of the 2025 NBA Finals
(Thunder vs Pacers): home win 58.2% / away 41.8%, summing to 100 with no
draw field at all; expected total 223.3; and the three lines monotonically
decreasing (75.3% / 48.3% / 26.2% over), a genuine check that each line is a
distinct calculation rather than one number repeated three times.

### Tennis — done, after the first source turned out to be gone

Tennis was reported blocked, then unblocked on a follow-up question. Both
halves are recorded here because the first answer was too quick to stop.

**What was blocked.** The intended source was Jeff Sackmann's ATP/WTA
dataset, which the project owner had cleared on licensing (CC BY-NC-SA 4.0,
non-commercial). It is gone: `api.github.com/repos/JeffSackmann/tennis_atp`
returns 404 and `user:JeffSackmann` now lists a single unrelated repository.
The surviving mirrors are not a substitute — `mare-imbrium/tennis-atp`
carries two years of a fifty-year dataset and relabels it **MIT**, which a
fork cannot legitimately do to CC BY-NC-SA material. Training on that would
have meant building on a foundation likely to be ripped out.

**What unblocked it.** The obvious source had been missed: this pipeline
already ingests 16 domestic leagues from **football-data.co.uk**, and the
same publisher runs **tennis-data.co.uk**. It is strictly better for this
project than the original plan — ATP and WTA from 2000, per-set scores,
surface, rankings, and **bookmaker odds**, which plug straight into the
existing value-detection and ROI paths. Ingested **75,867 matches**
(2010-2025, ATP + WTA).

**Two traps, both of which would have produced a confidently wrong model:**

- **Winner/loser leakage.** The source has `Winner`/`Loser` columns, not
  player 1/2. Loaded naively, the home player wins 100% of matches and a
  model "achieves" perfect accuracy having learned nothing. Slots are
  assigned by a deterministic hash of the match identity — stable across
  re-ingests, uncorrelated with the result. Measured home-slot win rate:
  **49.98%**. The winner trainer records that number every run, so a
  regression surfaces immediately rather than as a suspiciously good score.
- **Sets decide, games don't.** Total games were used as the score at first.
  Verifying the load caught it: a player can win fewer games and still win
  the match, so a games-based winner label was **wrong for 2.00%** of
  matches and **undefined for another 2.82%** — 4.81% corrupted labels, and
  421 matches with no definable winner at all. Fixed by storing *sets* in
  `home_score`/`away_score` (keeping "higher score won" true in every sport)
  and moving games to their own columns. Migration `e5f6a7b8c9d0`.

Two further columns were added because they are load-bearing rather than
decorative: `surface` (ratings are kept **per surface** — clay ability is
genuinely not grass ability) and `best_of` (WTA is always best-of-3 at 21.8
average games; ATP plays best-of-5 at Slams at 25.9, so a totals model blind
to format under-prices men's Slams).

**Results, and an honest negative one:**

| Market | Accuracy | Baseline | Real edge |
|---|---|---|---|
| Winner | 64.62% | 64.22% (always pick higher Elo) | +0.40pp |
| Total games 19.5 | 67.37% | 66.72% (majority class) | +0.65pp |
| Total games 21.5 | 59.90% | 55.15% | **+4.75pp** |
| Total games 23.5 | 64.90% | 55.88% | **+9.02pp** |

**The winner model does not meaningfully beat a plain Elo rule.** On 13,716
test matches the standard error is ~0.41pp, so +0.40pp is statistically
indistinguishable from zero. An earlier run on three years of data was
actually *worse* than the Elo baseline (63.79% vs 64.41%); more history
fixed the sign but not the significance. This is reported rather than
quoted as 64.62% because the baseline is the only thing that makes the
number mean anything — and it is a real finding about tennis: match outcome
is close to fully described by rating difference. The totals markets are
where the model genuinely adds value, since Elo ranks players but says
nothing about how long a match runs.

Live-verified end to end: a real ATP match returned a two-way split summing
to 100, monotonically decreasing total-games lines (61.0 / 43.9 / 32.5), and
visibly distinct overall vs. surface ratings for the same player (2126
overall, 1984 on the match surface) — which is the per-surface design doing
exactly what it exists for.

Still open for tennis: player **rankings** are in the source and not yet
ingested, and per-tour (ATP vs WTA) models are untried. Either could move
the winner market off the Elo baseline.

## Site rebuild against a reference product — done, in progress

The brief changed from "build a SaaS site around the engine" to "rebuild it
like nerdytips.com". That site was studied page by page in a browser and its
*structure* adopted; its palette was not. The visual identity stays dark
with gold accents, per the original brief and per an explicit decision when
the two conflicted.

The structural insight worth recording: **their board is a table with one
column per market**, not a list of cards with one prediction each. That
dissolves a tension this project spent several passes on — you do not choose
between "one prediction" and "show me more markets", you show a BEST TIP
column *and* per-market columns. Confidence is scored out of ten, not 0–100.

### What was built

- `app/services/settlement.py` — grades any call against a final result.
  Three outcomes, and the third carries the honesty: VOID, for a call about
  a stat the match does not record. Several competitions log no corners or
  cards; those calls were never settleable, so counting them either way
  makes the sample size a lie. Excluded from every rate, reported
  separately. An unrecognised market is VOID too — that is our omission,
  not the model's failure.
- `ml/competition_catalogue.py` — country, short name and tier for all 25
  competitions, 1:1 with the database. In code, not a migration: reference
  data that wants reviewing in a diff. Becomes a table when it outgrows a
  few hundred rows.
- `app/services/board_service.py` — a prediction becomes a table row.
  Readable slugs (`spain-vs-croatia-prediction-144414`) with the id on the
  end, so the name part is decoration and resolution stays exact.
- `app/services/progress_service.py` — the public track record, keeping
  live and backtested records strictly apart.
- `app/services/slip_service.py` — accumulator builder. One leg per fixture
  (two selections from one match are correlated), greedy and deterministic.
- `GET /board`, `/board/dates`, `/progress`, `/leagues`, `/bankers`, `/slip`.
  All added alongside the existing routes; none replaced.
- Pages: `/matches`, `/bankers`, `/slip`, `/leagues`, `/progress`, rebuilt
  home, new nav.

### Two bugs the rebuild surfaced

**The market columns were ranking by lift, not probability.** The 1X2 cell
preferred a 33% away win to a 45% home win because away beats its base rate
by more. `best_per_market` walked the lift-ordered list while
`headline_call` used probability — two rules, one row. Graded over 807
settled fixtures that column won 24.7%, against 33.3% for guessing, while
the headline beside it won 77.7%. Every market improved once both shared
one rule (`_pick` in `ml/markets.py`):

    market           was      now
    match_result    24.7%    51.5%
    double_chance   57.2%    76.2%
    goals           59.2%    71.9%
    corners         55.9%    72.4%
    cards           63.0%    76.0%

Found by building the track record, not by reading the code — the headline
number looked fine throughout. That is the argument for grading everything
rather than only the figure you lead with.

**Confidence is saturated** — see the open-items section above.

### Colour

`--color-won: #35b37e` and `--color-lost: #ec6a5e`, measured not chosen:
both clear AA on either surface (6.11 and 5.25 against the raised surface)
and sit 56.6 apart under a deuteranopia simulation, the widest of the
candidates tried. The reds that looked better on screen (#e0574f, #d9534f)
failed on the raised surface at 4.37 and 4.10. Green-versus-red is the pair
a red-green colourblind reader cannot separate, so neither is ever the only
carrier: every settled cell shows a tick or cross, screen readers get the
verdict in words, and the row carries a coloured edge as a third channel.

### Not built, and why

- **Log In, Hit&Win, subscription gating** — need auth, blocked on Supabase.
- **The match page's tabs and its predicted-vs-actual stats panel.** The
  strongest feature on the reference site: xG, possession, shots, corners,
  cards, offsides and fouls, each showing what was predicted against what
  happened. This engine predicts corners and cards and stores the actuals,
  so it is a genuine fit and the highest-value remaining UI work.
- **Team crests and flags** — needs an asset source.
- **Blog** — needs a content setup.
