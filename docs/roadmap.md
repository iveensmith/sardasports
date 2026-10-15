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

- **The best-tip column showed no price on most rows — fixed.** Sampled 150
  completed fixtures: 75% of headline picks were a double-chance call (1X,
  X2), a market no bookmaker line is fetched for at all, so `odds_for`
  returned `None` regardless of how well-priced the rest of the row was.
  Fixed properly rather than papered over — a double-chance price is exactly
  computable from the 1X2 prices already ingested (convert each leg to an
  implied probability, sum, invert), the same reasoning `candidate_calls`
  already uses to derive the double-chance *probability* from match-result
  probabilities. For the residual with no bookmaker coverage in any market
  (half-time goals, corners, cards headlines, or a fixture no bookmaker
  priced at all), the best-tip column falls back to the pick's own fair
  price (100 / probability) — computed from a number already on the row, not
  invented — and is flagged `odds_is_estimated` so the board can (and does)
  show it differently from a real market price rather than blur the two.
  The per-market columns make no such promise: they still show a bare gap
  where there is genuinely no data, which is the honest answer for a column
  that isn't the one thing a reader is told to trust most.

- **Double chance crowded out every other headline — rebalanced.** Asked
  directly for more variety in the best-tip column. The 75% figure above was
  a symptom of the same cause: a double chance is a sum of two match-result
  outcomes, so its probability starts inflated before the model contributes
  anything, and the flat `MIN_HEADLINE_LIFT` let it win the probability
  contest on that structural edge alone. `headline_call` already documents
  that banning it outright was tried once and made things worse — it just
  handed the same crowding-out problem to "Over 1.5 goals" instead. So
  rather than re-trying that, double chance now answers to a higher bar
  specifically (`DOUBLE_CHANCE_MIN_HEADLINE_LIFT = 20.0`, against the
  ordinary 5.0), tuned against the same 150-fixture sample: goals, match
  result and double chance now split close to evenly (30% / 29% / 27%)
  instead of double chance taking three in four rows, and match result — the
  market most readers actually relate to — went from 3% of headlines to a
  real share. Verified live: the same 29-fixture graded card that was 100%
  double-chance-headed earlier the same day now reads goals 34% / match
  result 28% / double chance 24% / half-time goals 10% / BTTS 3%. Per-market
  columns and the fixture-page table are unaffected — the higher bar only
  applies to who gets to lead the row, not to which selection represents
  double chance on its own.

- **Over/Under 3.5 goals — added.** Asked directly whether the engine trains
  for it. It didn't: `GOALS_LINES` only offered 1.5 and 2.5. The market is
  fully generic per line — a dedicated LightGBM classifier trained the same
  way as every other over/under line, blended with the same reused Poisson
  scoreline fit, `/predict`'s `goals_markets` array just picks up whatever
  `GOALS_LINES` lists — so this was a one-line addition plus training the
  new model (`train_over_under.py --line 3.5`): accuracy and log-loss land
  in the same range as the existing 1.5/2.5 models. Live-verified on a real
  fixture's `/predict` response and the match page's Goals table.

- **12 more leagues added, in two batches — Mexico, Russia, Poland, Norway,
  then Austria, China, Denmark, Finland, Ireland, Romania, Sweden,
  Switzerland.** Asked directly, twice, for wider coverage. Registered in
  `clean_data.py`, `competition_catalogue.py`,
  `ml/training/common.py` and `fetch_upcoming_fixtures.py`, then retrained.
  Surfaced two bugs along the way rather than papering over either:
  `fetch_extra_league.py` assumed every source's `Season` column used the
  same bare-year format, which Mexico/Russia/Poland's split-year style
  ("2019/2020") would have silently mis-written — fixed with per-row format
  detection (`_parse_season_value`/`_season_code`) instead of a per-country
  hardcode. And editing `KNOWN_COMPETITIONS` changes the one-hot feature
  vector's width, which the running FastAPI process keeps stale in memory
  regardless of whether the retrain succeeded — the board went to zero
  predictions after the first batch until this was understood. Now a
  standing rule: **any change to `KNOWN_COMPETITIONS` needs a backend
  restart before the next retrain's output can be trusted, independent of
  whether the retrain itself succeeded.**

- **A genuine light theme — not an inverted dark one.** Asked directly to
  use the frontend-design and dataviz skills properly rather than flip
  values. Built as its own token set under `:root[data-theme="light"]` in
  `globals.css`, with the dark tokens kept as explicit defaults (and a
  `[data-theme="dark"]` variant for the hero, which stays dark regardless of
  site theme — a `backdrop-filter`/gradient composition that only works
  against a dark ground). Every color pair was measured, not eyeballed:
  WCAG contrast computed directly, and the categorical palette (home / draw
  / away / won / lost) run through the dataviz skill's
  `validate_palette.js` for both modes. Two pre-existing dark-theme
  contrast bugs were found and fixed in passing — a hardcoded `#131313` and
  a hardcoded `#06090d` that should have been the new
  `--color-ink-on-accent` token — because they only became visible once the
  surface they sat on could also be light. Persisted via `localStorage`
  with a pre-hydration inline script in `layout.tsx` so there is no flash
  of the wrong theme on load. Live-verified in the browser on both themes.

- **The header broke completely below ~1024px — fixed.** Reported directly,
  with a screenshot: six nav links plus the theme toggle just wrapped at
  phone width, pushing items off the visible edge with no responsive
  handling at all. Added `MobileNav.tsx`, a hamburger overlay hidden above
  `lg:` (the desktop row is unchanged at that breakpoint). Its first version
  rendered the open panel inline in the header's own tree, which collapsed
  to zero height — `position: fixed; top-16 bottom-0` was resolving against
  the header's own 64px box, not the viewport, because the header's
  `backdrop-blur-md` (a `backdrop-filter`) makes it the containing block for
  any `fixed` descendant, same as `transform`/`filter` would. Fixed by
  portaling the panel to `document.body` with `createPortal`. Live-verified
  at a real ~500px window width: open/close, the icon swap, and tap-a-link-
  to-navigate-and-close all work. Audited every other page
  (`/`, `/matches`, `/bankers`, `/leagues`, `/progress`, `/slip`,
  `/leaderboard`) at the same width — each collapses cleanly, and every
  wide table (board rows, the model leaderboard) already scrolls
  horizontally rather than overflowing the page.

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

## Mexico, Russia, Poland, Norway; a real ceiling on "predictions today" — done, live-verified

Asked for coverage closer to the reference site's ~77 predictions on a given
day. Investigated before building: pulled the raw API-Football fixture list
for that exact day directly — 209 fixtures across 65 leagues, dominated by
women's competitions, youth academies (Brazil U17, Pernambucano U20),
reserve sides (Argentina Reserve League), and amateur divisions (Belgian
First/Second Amateur Division). None of that is a coverage gap this engine
can close without abandoning the rule the rest of this document is built
around: no fabricated prediction for a competition with no real historical
signal to train on. Matching 77 on a day like that would mean modelling
categories this project has deliberately never modelled, not adding leagues.

What's real: **four more legitimate senior leagues**, added the same way as
the Argentina/Brazil/Japan batch — Mexican Liga MX, Russian Premier League,
Polish Ekstraklasa, Norwegian Eliteserien (API-Football ids 262/235/106/103).
Found a genuine format gap in `fetch_extra_league.py` while pulling real data
through it: Mexico/Russia/Poland store their Season column as a split-year
string ("2019/2020"), not the bare year ("2019") Argentina/Brazil/Japan/MLS
use — the script only handled the latter, so it would have silently written
every one of these three countries' files under the wrong (same-year) season
code. Fixed by detecting the shape per row from the value itself rather than
assuming one convention per script, with 6 new tests pinning both shapes —
this script has now produced three distinct silent-data-loss bugs across two
sessions, which is what justified giving it a test file at all.

Loaded 7,764 new matches (dataset now **79,130 matches, 25 leagues**), Elo
rebuilt across 159,247 matches, every model retrained. Live-verified with a
real `/predict` call on a completed Liga MX match (UNAM Pumas vs Cruz Azul).

**Confirmed, not fixed:** none of the four had a fixture in the currently
visible window either — checked directly against the API. This is the same
international-break ceiling as everything else in this section: it isn't a
league-coverage problem on a week like this one, and these four will show up
the moment their own domestic calendars resume, same as every league added
before them.

## Austria, China, Denmark, Finland, Ireland, Romania, Sweden, Switzerland — done, live-verified

Asked to add the rest of the "extra" Football-Data.co.uk countries this
document had left open. Same pipeline as every batch before it — Austrian
Bundesliga, Chinese Super League, Danish Superliga, Finnish Veikkausliiga,
Irish Premier Division, Romanian Liga I, Swedish Allsvenskan, Swiss Super
League (API-Football ids 218/169/119/244/357/283/113/207) — with one naming
correction found along the way: Football-Data.co.uk calls Romania's top
flight "Superliga" (a sponsor name); API-Football calls it "Liga I", so the
competition is registered under the latter, the name actually used to look
it up for live fixtures. 11,989 new matches loaded (dataset now **91,119
matches, 33 leagues**), Elo rebuilt across 171,236 matches.

**Real bug, caught by the site itself rather than by testing it:** asked
directly why tomorrow's board had zero predictions. `Batch prediction failed
... operands could not be broadcast together with shapes (1,60) (68,)` —
adding 8 leagues' one-hot columns changes the competition-feature vector's
width, and the *running server process* had the old, 60-column
`KNOWN_COMPETITIONS` loaded in memory from before this batch's edits, while
the freshly retrained match-result model (correctly built against the new
68-column shape) expected the new width. Restarting the backend after
editing the source and retraining — not just after retraining — is the
actual rule; skipping the first restart is what caused today's board to go
to zero predictions too, not just tomorrow's, for exactly as long as the
stale process kept serving requests. This is the same dimension-mismatch
class of bug as the very first multi-league expansion earlier in this
document, from the same missed step, and is worth a standing note: **any
change to `KNOWN_COMPETITIONS` needs a backend restart before the next
retrain's output can be trusted, independent of whether the retrain itself
succeeded.**

Live-verified after the restart: today's and tomorrow's boards both went
from 0 to fully predicted, and real `/predict` calls against a Swiss Super
League, Danish Superliga, and Chinese Super League fixture each returned a
sensible, correctly-favoured prediction. 385 tests pass.

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
- **Team crests and flags** — needs an asset source.
- **Blog** — needs a content setup.

## Match page rebuild: tabs, the predicted-vs-actual panel, live goal events — done, live-verified

Asked directly for the reference site's match-detail page, "every single
thing." Two parts of that are impossible without either fabricating data or
new infrastructure, and both were said plainly before building anything:
a live goal-by-goal timeline needs real scorer/assist/minute data this
engine never ingested, and possession/offsides/fouls need real match
statistics it never ingested either. The agreed scope: ingest all of it for
real via API-Football's existing endpoints, predict what there's already
history to train on, and show the rest as actual-only rather than invent a
predicted number the model never produced.

**New ingestion, `scripts/fetch_match_stats.py`.** `fetch_results.py`
fetches only the final score for a fixture it closes out — its own
docstring already flagged statistics as "a deliberate follow-up, not an
oversight." This is that follow-up: two more requests per completed
fixture, at `/fixtures/statistics` and `/fixtures/events`, filling in
shots/shots-on-target/corners/cards (columns that existed but were never
live-fetched for a match this engine actually predicted — only the
historical Football-Data.co.uk bulk load ever populated them), three new
columns for possession/offsides/fouls, and a new `match_events` table for
the goals themselves. Scoped by a new `stats_fetched_at` timestamp rather
than "is `home_shots` null" — several competitions genuinely report none
of this, and without a separate "tried" marker every scheduled run would
re-request the same uncovered fixtures forever. Team assignment is by name
(`fold_team_key`, the same normalization the rest of the pipeline already
uses), not a stored API-Football team id, so it costs no extra request.
Wired into the scheduler ten minutes after `fetch_results`, so it only ever
sees fixtures that already have a score. Live-verified against 5 real
completed fixtures on a rate-limited free plan (Spain 4-1 Croatia came back
with all five goals, real scorers and assists, real HT score 2-1, real
shots/possession/corners/cards/offsides/fouls for both sides).

**`GET /predict/{match_id}` carries "what's actually true right now" for
the first time.** `match_status`/`match_score`/`odds_1x2` (all three
sports) and `ht_score`/`actual_stats`/`events` (football) are read straight
off the match row in the route, not the cached prediction service — the
same separation `value` already used, so a completed match's real score
doesn't get trapped behind the 10-minute prediction cache. `actual_stats`
is `null` until `stats_fetched_at` is set, genuinely distinct from a
completed match whose competition reports none of it (which comes back
with every field present and `null`).

**The predicted-vs-actual panel only claims a prediction where one exists.**
Goals is the only row with a real predicted figure —
`expected_goals_home`/`away` is a first-class model output. Corners and
cards are priced as over/under lines with a probability each, not a single
expected count, and interpolating one from those probabilities would be a
number the model never actually produced — so those, and
shots/shots-on-target/possession/offsides/fouls, are actual-only rows,
present only once there's something real to show.

**Form, H2H and Recent Matches needed no new data at all** — every
completed match this engine has on record was already enough. `GET
/matches` gained an `opponent` param (paired with `team`, either side) for
head-to-head, reusing the existing browse endpoint rather than a new one.
`GET /team/{team}` gained `over_1_5`/`over_2_5`/`over_3_5`/`btts` counts
(`ml.feature_engineering.features.compute_goal_rate_form`, a display-only
sibling of the training-facing `compute_team_form` next to it) for the Form
tab. Both `/team/{team}` and the whole `get_team_detail`/`TeamDetailOut`
path already existed in the codebase, unused by any page — this is the
first thing to actually read them.

Each non-"Match Tips" tab is its own further engine call
(`components/match/*`, orchestrated by `app/match/[id]/page.tsx`'s `?tab=`
query param), made only when a reader actually opens that tab rather than
on every page load. Also fixed in passing: the page's "back" link pointed
at `/predictions`, a route not in the site's nav at all — it now points at
`/matches`.

### The bars didn't match the reference's own mechanic — fixed, twice

Reported directly, twice. First pass: the predicted-vs-actual panel was a
plain two-colour split bar with "predicted X" as separate text underneath,
not the reference's real shape — one bar per stat, split at a shared centre
line, each side filling *outward* from it, both figures visible as marks on
the same track. Rebuilt to match: each side fills solid out to the smaller
of {actual, predicted}, then extends with a hatched texture (this site's
own "not a hard number" texture, the same one `BoardTable` puts on an
estimated price) out to the larger, so the gap between prediction and
reality reads directly off the bar. Checked against the reference's own XG
row (predicted 1.23/actual 0.81 one side, predicted 1.14/actual 1.97 the
other) to confirm the solid-then-hatch ordering reads correctly in both
directions.

Second pass, checking every other tab against the same reference now that
one panel was right: Form had the identical mismatch — "7/10" as plain
text, no bar at all, where the reference uses the exact same bidirectional
bar. Extracted the mechanic into `components/match/CenterBar.tsx` (was
duplicated inline in the stats panel) so Form and Predicted vs Actual share
one real implementation. Also brought H2H (a coloured left edge per
meeting, win/draw/loss from the queried team's perspective) and Recent
Matches (the W/D/L indicator moved from a summary strip only to one badge
per row as well) in line with how the reference actually reads down each
list. This site's own home/away colours are kept throughout rather than
the reference's single-hue vivid/muted-by-magnitude scheme, since every
other chart on the site already commits to fixed semantic colours
(`ProbabilitySplit`, `BoardTable`) — matching the reference's *mechanic*,
not re-skinning this product in its palette.

### Season statistics tab — done, live-verified

The reference's fifth tab, added once asked directly: per-match season
averages for both sides, on the same bidirectional bar. Needed one new
piece — `compute_season_stat_averages` in `team_service.py` — since
`get_team_matches_as_dicts` only ever carried scores, not the shot/corner/
card/possession/offsides/fouls columns already sitting on `Match`. "Current
season" is whichever season a team's most recent completed match falls in;
anything from an earlier season is excluded rather than blended in, and
each stat's `sample_size` travels with its value so a team can show a full
season of `shots` (a long-ingested historical column) alongside a
`sample_size` of 2 or 3 for `possession` (only real since
`fetch_match_stats.py` started running) without either looking like the
other's kind of number.

Two of the reference's rows are deliberately absent: **Expected Goals**
and **Total Passes**. This engine has no recorded xG independent of its own
pre-match prediction — averaging past predictions into a "season stat"
would present a model output as a recorded fact, exactly the blur this
product has refused everywhere else. Passes were never ingested at all, by
any source. Both are omitted entirely rather than shown empty or estimated.
Live-verified against Spain's real September 2026 fixture (16.0 shots/
match, 64% possession, sample sizes correctly at 1 this early in the
season for the fields `fetch_match_stats.py` only just started filling).

One unrelated bug surfaced and fixed while restarting services to pick up
the schema change: two backend processes were both bound to port 8000 from
earlier in the session, and concurrent writes from both against the same
SQLite file produced `database is locked` errors on `/predict`. Not a code
bug — a leftover process from an earlier restart — but a reminder that this
pipeline has no guard against two servers running at once.

### Recent Matches: the Total/Home/Away and Full Time/Half Time toggles — done, live-verified

The one piece of the reference's Recent Matches tab not yet matched, added
once asked directly. Checked the reference's own behaviour first rather
than guessing: Home/Away turned out to be a client-side filter of the same
last-10 list already fetched, not a deeper query (a "Home" click yields a
strict subset of the same dated rows "Total" already showed) — so no new
backend data was needed for that half. Half Time was the real gap: the
engine already stores a half-time score (`Match.home_ht_goals`/
`away_ht_goals`, same "Half-time goals" column the season-stats tab reads
for other things) but `recent_matches` never carried it. Added
`home_ht_score`/`away_ht_score` to `RecentMatchOut`, `null` wherever the
source never recorded one — the same competitions that go without a
half-time score anywhere else in this product.

`RecentMatchesPanel` became a client component (`components/match/
RecentMatchesPanel.tsx`) with two independent toggles per side, matching
the reference exactly: switching to Half Time doesn't just swap the printed
score, it recomputes each row's W/D/L result from that score too — a match
led at half-time and drawn by full-time is a different result either way,
and showing the wrong one would misrepresent what actually happened at
that point in the game. A match with no half-time score on record shows
"—" and a neutral marker in that mode rather than a fabricated 0-0.

Caught one real staleness bug while verifying: Next's `getTeam` fetch
cache (`revalidate: 300`) served the pre-change response shape after the
backend picked up the new fields, rendering `undefined-undefined` for
every score until the dev cache was cleared and both servers restarted
clean. Not a code bug in the new feature — a reminder to always clear
`.next` after a backend schema change lands mid-session, which this
project has hit before.

## Below the fold on the home page — done, live-verified

Asked directly to do what the reference does below its own picks boards:
a track-record narrative, a "how it works" explainer, and an FAQ. The
reference also has a YouTube explainer, a "trusted by" strip of media
logos, Trustpilot reviews, and paid subscription tiers in that same
stretch of the page — none of which this product has a real one of, and
all four would have to be invented to fill the same slots. They're left
out entirely rather than faked: no video, no partner logos, no reviews
(fabricated testimonials are exactly the kind of "presented as genuine"
content this assistant refuses to produce), and no pricing tiers for a
subscription this product doesn't sell and has no payment infrastructure
for (subscriptions/Hit&Win are still blocked on the Supabase decision
noted earlier in this file).

What *is* real gets built from it instead:

- **`components/home/AboutTheEngine.tsx`** replaces the reference's
  reviews-and-logos slot with the engine's own numbers, as props rather
  than a guess — settled calls, win rate, competition count, and country
  count, each pulled from `/progress` and `/leagues`, both already fetched
  elsewhere on this page. A stat with nothing behind it (a fresh deploy,
  the engine unreachable) shows "—", the same rule the board itself
  follows, and the backtest/live distinction already established on the
  hero carries through into the copy here too.
- **`components/home/HowItWorks.tsx`** is the reference's three-step
  explainer, rewritten in this engine's actual terms (real data ingestion,
  leakage-safe feature engineering, the three-estimator ensemble) rather
  than its wording. Static — it describes a process, not a measurement, so
  it has no live number to go stale.
- **`components/home/Faq.tsx`** answers the reference's own question set
  honestly for this product: free with no login, the full record including
  losses is public, what the confidence score actually measures (estimator
  agreement, not a win probability), no bookmaker links, no fixed matches.
  Two answers are dynamic (real win rate, real league coverage) and fall
  back to a qualitative line rather than a fabricated number if the engine
  is unreachable. Built on `<details>`/`<summary>` rather than a client
  component with its own state — an accordion is what that element already
  does, for free, with working keyboard and screen-reader behaviour.

No backend changes — every number already existed on `/progress` and
`/leagues`; this is the first page to read some of them in prose rather
than a table. Live-verified in both themes: 29 settled calls, 89.7% win
rate, 40 competitions, 32 countries, since August 2015.

### The footer — done, live-verified

Pointed out directly that the reference's footer hadn't been matched.
Checked it in full: a brand column with social icons and three app-store
badges, a "Top Leagues" column (dedicated SEO landing pages), a "Matches"
column, a "Company" column (Tutorial/About Us/Contact Us/Recommended
Sites/Privacy Policy/Terms and Conditions), a two-column "Popular Teams"
link farm, a support email, a named legal entity, and a responsible-
gambling disclaimer bar.

This product has no real version of most of that — no social accounts, no
mobile app, no About/Contact/Privacy/Terms pages, no support inbox, no
per-team or per-league landing pages, no legal entity. Wiring up links to
pages that don't exist, or inventing generic Privacy/Terms text with no
real company or data-handling practice behind it, would be worse than not
having the section at all. `components/SiteFooter.tsx` keeps only what's
real: the site's own nav links (already on the header), a "Top leagues"
column built from the six competitions with the most completed matches on
record (`getLeagues()`, sorted by `completed`, linking to the same
`/matches?competition=` filter the leagues page itself already uses — not
a dedicated page), and a plain disclaimer bar restating facts the rest of
the site already asserts (informational only, no bookmaker links,
probability not certainty) rather than nerdytips' gambling-helpline links
or an invented legal entity name.

An async Server Component, not a client one — its one live dependency
(`getLeagues()`) only needs to run once per render, and if the engine is
briefly unreachable the "Top leagues" column disappears rather than
showing stale or guessed data, the same `EngineError`-only catch pattern
used elsewhere on this page. Live-verified on both the home page and a
second page (`/matches`) to confirm it renders identically everywhere via
the root layout, in both themes, and that a real league link
(`/matches?competition=English+Premier+League`) correctly filters the
board rather than 404ing.

## Typography: Red Hat Display/Text — done, live-verified

Asked directly to replace Archivo, which read as flat and generic. The
replacement went through two candidates, and the first one's failure is worth
keeping on record so it isn't rediscovered:

- **Schibsted Grotesk — rejected.** Chosen for its editorial/data heritage,
  but its Google Fonts build has a broken comma/period glyph: a visible extra
  space before every comma and full stop, at every weight tried (400/420/700,
  static and variable instances). Reproduced in an isolated test `<div>` with
  plain inline styles, outside anything in this codebase, so it is a defect in
  the font file as served, not something fixable from this project's config.
  **Do not retry it.**
- **Red Hat Display + Red Hat Text — adopted.** An actual display/text pair
  rather than one family stretched over both jobs, built for dense technical
  interfaces where numbers are compared constantly. Display
  (`--font-display`) carries headlines, `h1`–`h3` and hero numbers; Text
  (`--font-body`) carries body copy, labels and table cells. Both are loaded
  as true variable fonts via `next/font/google` in `web/app/layout.tsx`, with
  no `weight` array so intermediate weights are real rather than rounded to
  static instances.

If the face is ever revisited, Instrument Sans and Public Sans were also
checked in the same isolated test and showed no punctuation defect.

### Housekeeping in the same pass

- `tests/test_scheduler.py` still expected the pre-rebuild job list and was
  failing on `fetch_match_stats`, the job registered with the match-page
  rebuild. Expected set updated; the suite is otherwise green (421 tests).

## Track record page, step 2: the reference's missing pieces — done, live-verified

A side-by-side of `/leagues` and `/progress` against the reference found
`/progress` ahead on breakdowns (by market, confidence, competition — the
reference has none) and behind on five things. Built the ones that can be
backed by real data:

- **The backtest caveat no longer disappears when one live call arrives.** It
  was gated on `!hasLive`, so a single live prediction hid it and relabelled
  the blended figure "Overall" — a 77.8% headline that was 99% backtested
  read as a published record. The headline is now two cards, Backtested and
  Live record, never blended, and the caveat stays for as long as backtested
  calls are counted. The home page's About section had the same root cause:
  it dated a live-only record from the backtest's first match.
- **Monthly table and a last-12-months chart.** Every one of the twelve
  calendar months gets a row, including empty ones ("no settled calls"), and
  each carries how many of its calls were live (`live_settled`, new on
  `by_month`). The chart plots all twelve months and breaks the line at gaps
  instead of bridging them. The record is sparse — predictions exist only
  where the engine was asked to price a fixture — and a chart that closed
  the gaps drew a slope across months that were never measured.
- **"Newest settled match" line.** States the date of the newest settled
  match and how long ago it was, and says anything played since is not in the
  figures. It needs no new data, and it makes staleness visible instead of
  implicit.
- **Two CSV downloads**, `GET /progress/daily.csv` and `/progress/matches.csv`
  (proxied by the web app, so the engine's address stays server-side). Both
  are produced from the same `_grade_all` rows the page uses, and
  `tests/test_progress.py` pins that they reconcile — daily settled/won/lost
  sum to the page totals, match rows count the same outcomes. Checked against
  the real database: 490 daily rows summing to 1,981 settled, and 1,983 match
  rows (1,542 won, 439 lost, 2 void).
- **A FAQ**, with `FaqItem` extracted so the home page and this page share
  one accordion item. Two answers state limits the reference doesn't: that
  backtested calls are the fixtures the engine was *asked* to price (stored
  on demand), not every match played and not a random sample; and that the
  record is as current as the last ingest, not on a fixed clock.

**Left out on purpose:** the reference's 14-day "recent form" line. The live
record is one day's calls, so a daily line over it is a single point, and
drawing it from backtested days would present a reconstruction as recent
form. It becomes honest once the live record spans a few weeks. A **Bankers**
rate beside Overall also waits on a decision: `/bankers` selects on
probability, not confidence, so a historical Bankers record needs a
deterministic rule written down first.

**Found while verifying — ingestion is not running.** `.env` has
`ENABLE_SCHEDULER=false`, so none of the scheduled jobs (fixtures, odds,
results, match stats) run when the backend starts; nothing has been ingested
since 2026-10-01, and fixtures from 2026-09-28 to 2026-10-01 are still marked
`scheduled`. A free API-Football plan serves only about three days back, so
those results are probably not recoverable. Turning the scheduler on is a
deliberate call, not a fix to make silently: it spends API quota on a free
plan, and the roadmap records an earlier concurrent-write problem between
scheduled jobs and manual runs.

Also re-confirmed: after a backend schema change, Next's fetch cache
(`revalidate: 3600` on `/progress`) serves the old JSON shape for up to an
hour and crashes any component reading a new field. Clearing `.next` and
restarting the dev server fixes it; it is a dev-time trap, not a code bug.

## Per-league pages — done, live-verified

The reference's biggest structural advantage over `/leagues` was that every
competition has a page of its own. Built `/leagues/[slug]` for all 40
competitions, backed by `GET /leagues/{slug}` (`app/services/league_service.py`).
The index at `/leagues` gained flags, links to those pages, a search box and
a "Most match history" row — ranked by history rather than called "popular",
because popularity is not something this site measures.

What a league page carries, all counted from matches the engine holds:

- Matches on record, teams in the latest season, and the result split and
  Over 1.5/2.5/3.5/BTTS rates across every completed match.
- **The engine's own record in that competition, with live and backtested
  kept apart** — the same rule as the track-record page.
- A Standings tab (the `/standings/{competition}` logic, finally used by a
  page) and Match Predictions: upcoming fixtures priced the way the board
  prices them, and the latest results on record.
- Hottest and coldest team over the last five results, with the rule printed.
- A summary paragraph built only from those numbers.

**Honesty rules the page enforces:**

- **It says how current it is.** A competition whose newest result is more
  than 45 days old gets a banner stating the date of that result and how long
  ago it was, and hot/cold teams are *not named* — the last five matches would
  be last season's, and "hot" would describe a past year as now. A table is
  still shown, captioned with its season and the result it runs to.
- **International competitions get no table and no form.** A table of
  friendlies, or of qualifiers over two years, is not a table of anything.
- A rate over nothing is a dash, never 0%.

**Left out on purpose:** the reference's "constant" team (its criteria are
undisclosed and we would be inventing a definition), "predictability rate"
(a claim about accuracy we would have to measure to make), team crests (no
licensed source), and any "700+ competitions" style claim. A recent-results
list shows plain results with no pick beside them: where the engine never
priced a match there is no call to grade, and viewing a past fixture's pick
would *create* a backtested prediction as a side effect of reading a page.

### What building it exposed

**No domestic league has a result newer than 127 days; most are about 500
days old.** Premier League, La Liga, Bundesliga, Serie A, Ligue 1 and the
other European leagues end at the close of 2024-25 (25 May 2025); the
calendar-year leagues end in 2025. Only international football is current
(the 29 September 2026 internationals). So every domestic league page shows
last season's table and a stale-data banner, and the board has no domestic
fixtures to price. This is the same root cause as the stale track record:
`ENABLE_SCHEDULER=false`, plus the Football-Data.co.uk CSVs never having been
re-downloaded for 2025-26. It is the highest-value open item in the repo and
it needs an owner decision, since it spends API quota.

**Calendar-year seasons are stored under unreadable codes** — Argentina's,
Brazil's, Japan's and others' 2025 is `"2525"`, and MLS's is `"2025-2025"`.
Normalised for display by `season_label` and left alone in the database, since
the value is a key and changing it rewrites history. The cause is almost
certainly the split-year decoder in `clean_data`/`fetch_extra_league` reading
"25"+"25" as a pair; worth fixing at the source when those scripts are next
touched.

`tests/test_league.py` pins the recency gate, the dash-not-zero rule, the
international exemption and the slug round-trip.

## Domestic data refreshed to October 2026 — done, live-verified

Every domestic league had stopped at the end of 2024-25 (calendar-year
leagues at 2025), because the Football-Data.co.uk CSVs were never re-downloaded
and the scheduler is off. That source is free and uses no API quota, so it was
the right first fix. API-Football's free plan is 100 requests/day, 10/minute
(checked via `/status`, which is free). The scheduler as configured would
exceed that: by the code, fixtures cost ~42/day (6 runs × 7 dates), results
~24 (8 × 3), odds 18–54 plus up to 40 fallback requests per run, match stats 2
per fixture, and the injury sync loops over all 3,467 teams — tennis players
included, with only one cached API id — so at least 3,467 requests, which alone
exhausts the quota. It needs rebudgeting (fewer runs, `--days 3` to match the
free window, injuries off or limited to teams in upcoming fixtures) before
`ENABLE_SCHEDULER` is turned on. Counts are from reading the code, not a
measured run.

**What was loaded.** 2025-26 and 2026-27 for the 16 main leagues, and 2025/2026
for the 16 extra countries (`fetch_extra_league.py`, with the League filter
confirmed per country first: MLS, Liga Profesional, Serie A, J1 League, Liga MX,
Premier League [Russia], Ekstraklasa, Eliteserien, Bundesliga [Austria], Super
League [China and Switzerland], Superliga [Denmark and Romania], Veikkausliiga,
Premier Division, Allsvenskan). 8,821 new matches inserted; the dataset is now
100,075 football matches and Elo was rebuilt over 180,059 completed matches.
Newest results are now 0–18 days old for every domestic league except the
Saudi Pro League (138 days — it comes from API-Football, not this source) and
the Russian Premier League (65 days, a genuine summer break).

**A real defect the load would have caused, fixed in the loader.**
`load_to_db.py` recognised matches by `external_id` alone, so a CSV row for a
fixture the API had already ingested (different id, bare date instead of a
kick-off time) would have been inserted as a second match, leaving the
original — which owns the predictions made before kick-off — scheduled
forever. A dry run found two such fixtures, both with live predictions
(Leganés–Castellón, NY Red Bulls–St. Louis City). The loader now matches
`apif-` fixtures by competition, team pair and a one-day date tolerance, and
completes them from the CSV row instead of duplicating them: the API's id,
kick-off time and any stats it already recorded are kept, and only empty fields
are filled. Both fixtures completed with their predictions intact.
`tests/test_load_to_db.py` pins this, including idempotence and that a
same-team fixture weeks apart, or in another competition, is *not* merged.

**Retrained all 12 football models.** Accuracy is essentially unchanged —
expected, since this adds history rather than changing the problem:

    match result 49.3% (was 49.6)    goals 1.5  75.8% (76.4)
    goals 2.5    56.2% (56.5)        goals 3.5  70.4%
    half-time    71.2% (71.1)        BTTS       55.2% (54.5)
    corners 7.5/8.5/9.5   72.9 / 61.2 / 54.5%
    cards   2.5/3.5/4.5   78.1 / 63.1 / 60.4%

`KNOWN_COMPETITIONS` did not change, so the restart rule did not bite; the
backend was restarted anyway to load the new models.

**Not refreshed, and why:** the Saudi Pro League and every international
competition come from API-Football, not this source, so they are unchanged —
international football is still current only to 29 September 2026 from the
earlier API pulls. Both wait on the paid plan.

**Found, not fixed (split into its own task):** 72 fixtures are stored twice —
34 German 2. Bundesliga, 19 friendlies, 14 Nations League, 5 Euros — because a
team name such as "Preußen Münster" is decoded two different ways between
pipeline runs and `external_id` embeds the name. All 72 predate this refresh
and the load added none. They double-count in tables and rates. Same family as
the Curaçao U+FFFD defect above.

A pre-load backup of the database (130 MB, integrity-checked) was taken to the
session scratchpad, not the repo; it is not a durable backup.

## English League One, League Two and National League — done, live-verified

Added as full competitions, the same way every earlier batch was: Football-Data.co.uk
codes `E2`, `E3` and `EC`, registered in `download_data.py`, `clean_data.py`,
`ml.competition_catalogue` (tiers 3, 4 and 5), `ml.training.common.KNOWN_COMPETITIONS`
and `fetch_upcoming_fixtures.LEAGUE_ID_TO_COMPETITION`. The API-Football ids
(41, 42, 43) were confirmed against `/leagues?country=England` rather than
recalled, because a wrong id would have filed another league's fixtures under
these names; that cost one request of the day's 100.

18,065 matches loaded, 2015-16 through 2026-27 (6,010 League One, 6,062 League
Two, 5,993 National League). The dataset is now 198,124 completed matches
across 3,579 teams; competitions went from 40 to 43. Clubs that move between
tiers (Birmingham, Wigan, Barnsley and 27 others shared with the Championship)
resolve to a single team row, so their Elo carries across promotion and
relegation. Verified: no football club is stored under more than one row, and
the same-day duplicate count did not move from 72.

**Per-stat availability, not per-league.** League One and League Two carry
corners, cards, half-time scores and odds throughout; the National League has
cards, half-time scores and odds but corners for only about 12% of matches, so
its corners market degrades to unavailable rather than being priced from
almost nothing.

Adding three competitions widens the one-hot feature vector, so all 12
football models were retrained and the backend restarted — the standing
`KNOWN_COMPETITIONS` rule applied this time. Accuracy is unchanged within
noise: match result 49.2%, goals 1.5/2.5/3.5 at 75.7/55.6/70.7%, half-time
70.7%, BTTS 55.1%, corners 73.3/61.8/54.0%, cards 77.3/59.5/61.1%. A real
`/predict` on a League One fixture returns all goals lines and corners.

**A mojibake name caught on the way in.** The National League source carries
`King\x92s Lynn` — a cp1252 apostrophe read as latin-1 — and loading it as-is
would have created a team named with a control character. `normalize_team_name`
now repairs exactly the cp1252 smart quotes and dashes (U+0091–U+0094, U+0096,
U+0097) and nothing else. It is deliberately narrow: the 34 existing ids that
contain mojibake use a different byte (`\x9f`), and a broader "repair cp1252"
pass would have rewritten those names and so re-inserted their matches as
duplicates. Whether any stored name or id contained the repaired characters was
checked first (none did). The general decoding defect is a separate task.

The web gained `tierLabel`, so a third-tier league reads "3rd tier" instead of
only the second tier being labelled.

**Side effect worth knowing about: viewing a board creates backtests.** The
refresh made 5–6 October results available, and rendering a board that includes
them stored six predictions (ids 2018–2023) on already-completed Argentine and
Spanish fixtures — correctly counted as backtested, since they were made after
the match. That is the existing mechanism, but it means the backtested record
grows when pages are browsed. One further prediction created by a manual
`/predict` verification call was deleted again. If the backtest figure should
only reflect deliberately generated predictions, board rendering should stop
storing them for completed matches; that is a decision, not a fix.

## Lower divisions and domestic cups, seven countries — built, waiting on the subscription

Asked for every lower division of England, Spain, Germany, Italy, France, the
Netherlands and Portugal, and their domestic cups, so the engine can predict
them. Football-Data.co.uk publishes none of it (the free source's `P2` code,
which looks like Portugal's second tier, serves *Spanish* Segunda División
files byte-for-byte — never add it), so all of it comes from API-Football. The
data pull is blocked on the plan; everything else is built, tested against real
payloads, and switched off.

**What exists.** `ml/api_competitions.py` registers 119 competitions (106
league divisions, 13 cups) from `/leagues?country=…` discovery — ids and season
ranges came from that data, never from memory. `scripts/fetch_api_competitions.py`
ingests them (one request returns a whole competition-season: 126 Copa del Rey
fixtures, 308 Segunda Liga). `--plan` prints the cost without spending any:
**901 requests for the full history of every core competition, 503 for
2022–2026.** The free plan is 100 a day, so that is nine days free or one run
on a paid plan.

**Families.** A tier split into regional groups — Spain's 18 Tercera RFEF
groups, Germany's 14 Oberligas, France's 13 National 3 groups — is one league
statistically but needs a table per group. So `name` is per group while the
one-hot feature and the Poisson fit use `family`: 119 competitions cost 34
feature columns, not 119. `fit_pool` and `one_hot_competition` both resolve
through `family_of`.

**Nothing is enabled.** Adding a competition widens the feature vector, which
needs a retrain and a restart (the standing `KNOWN_COMPETITIONS` rule), so a
registered competition does nothing until `ENABLED_IDS` is flipped — in the
same change that carries its data and the retrained models. With it empty, the
feature schema is unchanged (pinned by a test).

**Four decisions that are easy to get wrong, each checked on real data:**

- **Cups settle on the 90-minute score.** The API's `goals` includes extra
  time. The Copa del Rey final was Barcelona 3–2 Real Madrid after extra time;
  the 90-minute score, which is what 1X2 is about, was 2–2. About one
  single-leg cup tie in six goes beyond 90 minutes (22 of 126 in Copa del Rey
  2024) and every one of those is level at 90, so using `goals` would have
  mislabelled the 1X2 outcome of all of them. In a *two-legged* tie it is the
  aggregate that triggers extra time, so a second leg's own 90-minute score need
  not be level: a 2024-25 Champions League qualifier went to penalties after a
  0–1 second leg. Reading `score.fulltime` is right in both cases; assuming
  "level at 90" would not have been.
- **Neutral ground.** Every cup final, and the FA Cup semi-finals (Wembley), are
  flagged neutral so Elo gives neither side a home edge.
- **Season labels come from the competition, not the batch.** A first version
  inferred split-year from the earliest match in hand, so a partial refetch of
  just April's cup final was labelled "2024" instead of "2024-2025" and slipped
  past duplicate detection. `split_year` is now a registry fact taken from the
  season start dates the API publishes.
- **Club identity is a matching problem, not a similarity search.** Only 36 of
  125 Copa del Rey clubs matched an existing team by name; the misses included
  Athletic Club (ours: Ath Bilbao), Celta Vigo (Celta), Atletico Madrid (Ath
  Madrid) and Espanyol (Espanol). Fuzzy matching against the database is
  *unsafe* — it paired "Atletico Madrid" with Brazil's "Atletico-MG" and
  "Chiclana" with "China". Instead `app/services/team_identity.py` pairs a
  league's API roster with our roster for the same season one-to-one
  (`--map-teams`), where even a weak resemblance is decisive because every wrong
  answer is already claimed. On La Liga, Serie A and the Bundesliga that
  paired 58 of 58 clubs correctly and flagged the one genuinely new club
  rather than force it. After mapping, the Copa del Rey's top-flight clubs
  resolve to their existing rows and the 89 clubs it would have created fall to
  82 — all small clubs from tiers not yet ingested, which resolve by API id
  once their own league is. Every created club is written to
  `data/processed/api_new_teams.csv` with the existing club it most resembles,
  because a created row is either new or a missed alias and only a person can
  tell which.

**The live feed had the same defects, now fixed.** `fetch_upcoming_fixtures.py`
matched clubs by folded name only and otherwise created a new team at the
default 1500 — its own comment called the result "a default-rated coin-flip" —
so the first Athletic Club fixture would have been a new club, not Ath Bilbao.
It also discarded reserve sides with a `B`/`II` filter (Bayern II plays in the
3. Liga, Real Madrid Castilla in the Primera Federación), labelled seasons
"2026" beside a history that says "2026-2027", and didn't know cup finals are
neutral. It now uses the shared resolver, keeps reserve sides in registered
competitions, extends each competition's existing season-label shape
(`app/utils/seasons.py`: "2026-2027", doubled "2626", bare "2026"), and flags
neutral rounds from the registry.

**Known limits, stated plainly:**

- **Cup predictions will be weaker than league ones until measured.** Two-legged
  ties (Copa del Rey and Coppa Italia semi-finals) are modelled as independent
  matches — second-leg aggregate state is not a feature. Cups cross tiers, and
  Elo only calibrates across tiers through promotion, relegation and the cup
  matches themselves. Clubs below the lowest tier registered (Spanish regional
  leagues, German Verbandsligen) enter at a default rating and should be treated
  as thin data. Run `scripts/elo_calibration.py` on the cups once data lands,
  and do not quote their accuracy before that.
- **Corners, cards and shots are unavailable** for all of these: the fixtures
  endpoint carries scores and half-time scores only, and statistics cost two
  more requests per fixture. The markets degrade to "unavailable", as they do
  for MLS and the Saudi league.
- **Deliberately not registered:** super cups (a handful of matches a year is a
  feature column fitted on noise), youth, reserve-only and women's competitions,
  and play-off rounds. Secondary cups (EFL Trophy, FA Trophy, Coppa Italia Serie
  C/D) are registered `extended` and fetched only on request.
- **The Leagues index will list every group.** Enabled, Spain alone adds 29
  entries to its card. It wants grouping by family with the groups collapsed;
  that is UI work deferred until there is data to design against.
- `--map-teams` defaults to the last two seasons. A club that fell out of our
  top tiers years ago and now plays in an API-only division only gets its id if
  that older season is mapped too, so run it as `--seasons 2016-2025`.

**Runbook for the day the plan is upgraded:**

1. `scripts/fetch_api_competitions.py --map-teams --seasons 2016-2025 --max-requests 600`,
   then read `data/processed/team_mapping_review.csv`.
2. `--plan`, then `--scope core --max-requests 1000` (about 900 requests).
3. Read `api_new_teams.csv`. Rows with a `resembles_existing` value are
   candidate aliases; add the real ones to `ALIASES` or fix the mapping, and
   re-run so they merge before ratings are built.
4. Set `ENABLED_IDS` to the core ids, retrain all 12 football models, restart
   the backend, then run the Elo calibration on the cups.
5. Rebudget the scheduler (see the data-refresh section) before enabling it.

Used about 15 of the day's 100 free API requests on discovery, one real cup and
one real league sample, and three club rosters for the matching experiment.
`tests/test_team_identity.py`, `tests/test_fetch_api_competitions.py` and
`tests/test_live_fixture_identity.py` pin all of the above, using trimmed real
payloads in `tests/data/api_football_sample.json`.

## UEFA club competitions registered — built, waiting on the subscription

Champions League (id 2, seasons 2011–2026), Europa League (id 3, 2014–2026) and
Conference League (id 848, 2021–2026) are in the registry alongside the domestic
cups, taking it to 122 competitions. Ids and season ranges come from the saved
`/leagues?country=World` discovery response, not memory. They add 35 requests
for their whole history; the full core scope is now **936 requests** (518 for
2022–2026). Like everything else in the registry they are disabled until data
and retrained models exist.

Left out on purpose: the UEFA Super Cup (one match a year), the Youth League
and women's competitions, and the national-team qualifiers (World Cup and Euro
qualification, Finalissima), which belong to the "all international matches"
work, still to do.

**What a real Champions League season looks like** (2024-25, 279 fixtures, 81
clubs, one request): qualifying rounds are *included* — 90 of the 279 matches
are the 1st to 3rd qualifying rounds and the qualifying play-off — then the
eight-match league stage, the knockout play-offs, and the knockouts. The
qualifiers pull in small clubs from across Europe with no history here; they are
ingested as results all the same and will arrive as thin-data clubs, so expect
the new-clubs report for these competitions to be long.

**A claim of mine was wrong, found by reading the real data.** I had written that
every cup tie that goes to extra time or penalties is level after 90 minutes.
That is true of a single-leg cup (all 22 in Copa del Rey 2024), but in a
two-legged tie it is the *aggregate* that triggers extra time. Ballkani v UE
Santa Coloma went to penalties after a second leg whose 90-minute score was
0–1; the API's headline `goals` for it is 1–2. Reading `score.fulltime` was
already right in both cases — only the explanation was overbroad — and it is
corrected in the registry docstring, the ingest script and the section above.
The case is pinned in a test using the real fixture.

**Not the same as "international".** The catalogue files these under "Europe"
beside the Euros and the Nations League, which makes `is_international` true for
them, but they are made of clubs. The league page no longer tells a reader that
"a national-team competition has no fixed set of clubs" about the Champions
League: the API now carries `national_teams` separately, and the page says the
field "changes every season" instead. They are also kept out of the
national-team Poisson pool (pinned by a test). Like any competition under an
international group they get no standings table; the league phase has one in the
new format, but a table spanning qualifiers, a league phase and two-legged
knockouts is not a table of anything.

**Neutral ground:** the final only, flagged from the round name (the 2025 final,
PSG 5–0 Inter, was at the Allianz Arena). The semi-finals are two legs, home and
away.

## National-team competitions registered, and a stored-score bug corrected

Asked for "all international matches available". The registry now carries 44
men's senior national-team competitions (kind `national`), taking it to 166
entries: the World Cup and the six confederations' qualification (29–34), the
Euros, Copa América, AFCON, the Asian Cup, the Gold Cup, the OFC Nations Cup, the
Nations Leagues (UEFA and CONCACAF), the Confederations Cup, the Finalissima,
the Arab, Gulf, ASEAN, SAFF, EAFF, CAFA, COSAFA and CECAFA tournaments, the
Caribbean Cup, the invitationals (China, Kirin, King's, Malta), and the
Friendlies feeds. Seven were already in the engine and are registered
`already_modelled`, so the same ingest can deepen their history without giving
them a second feature column. The full national scope is 312 requests of history
(132 for 2022–2026); the whole core scope is now 162 competitions, 1,248
requests. Like everything in the registry they are disabled until data and
retrained models exist.

**Excluded:** youth (U-17 to U-23), women's, club tournaments and multi-sport
games (the Olympics, Asian Games, Pacific Games and so on), and competitions
whose status I could not establish from the listing (The Atlantic Cup, Como
Cup, COTIF). Those can be added once someone has looked at what they are.

**How they fit the model.** National teams share one international Poisson pool
and are weighted by an Elo K, so each registry entry carries a K. They reuse the
four tiers the first seven were calibrated on — 90 World Cup, 80 continental
finals, 70 competitive fixtures at full strength, 45 friendlies and invitationals
— and no new numbers. That is a judgement by category, not a fit: 22
competitions are at 70 and 13 at 45, and neither assignment has been tested.
Run `scripts/elo_calibration.py` before trusting them. Minor tournaments share a
family (Regional, Invitational, Intercontinental; the six World Cup qualifying
groups are one), so a few dozen matches do not get a feature column of their
own: nine new columns for 37 new competitions. Tournaments hosted by one nation
are neutral throughout, which carries the host-nation approximation the first
seven already had; qualifiers and the Nations Leagues are home-and-away.
`INTERNATIONAL_COMPETITIONS` and `INTERNATIONAL_ELO_K` both extend from the
registry, and the existing assertion that they agree still holds.

### A stored-score bug in the existing international data — fixed

`scripts/fetch_international.py` read the API's headline `goals`, which includes
extra time, and its comment called that "the right thing to train on". It is not:
the 1X2 market is about the 90-minute result. Re-fetching the seasons it had
loaded and comparing with the database found **28 matches that went beyond 90
minutes, 10 of them stored with the extra-time score** — including the 2022 World
Cup final (stored 3–3, 2–2 at 90 minutes), Spain–Germany at Euro 2024 (2–1 vs
1–1), Croatia–Brazil (1–1 vs 0–0), Netherlands–Croatia and Portugal–Denmark in
the Nations League, and Argentina–Colombia at Copa América.

- **Source fixed.** The loader now reads `score.fulltime` through a pure
  function (`ninety_minute_score`) tested on the real final, falling back to
  `goals` only for a payload with no `fulltime`.
- **Data corrected.** The registry ingest now corrects a held match that went
  beyond 90 minutes and carries the wrong score — and only such a match: an
  ordinary result is never rewritten (pinned by a test). Run against the saved
  payloads it corrected exactly the 10 and inserted none. Elo was rebuilt over
  198,124 matches. A pre-correction backup is in the session scratchpad.
- **Not yet done:** the 12 football models were not retrained for ten changed
  labels among ~198,000 matches; that happens at the next retrain, which enabling
  these competitions needs anyway. The raw files in `data/raw/` still hold the old
  scores, so rebuilding a database from scratch with the old CSV pipeline would
  reintroduce them — re-run `fetch_international.py` (the fixed version) first.

Deep history is limited by the plan: the free tier serves seasons 2022–2024, so
the World Cup qualifying cycles before that, and every pre-2022 friendly, wait
on the subscription — which would roughly quadruple the thin international pool,
the single highest-value data job in this repo (see the known defects above).
`tests/test_fetch_international.py` and additions to
`tests/test_fetch_api_competitions.py` pin all of this using real World Cup 2022
fixtures.

## The home page's results strip disappeared — fixed

Reported: the scrolling strip of recently settled picks was gone from the home
page. It is a real regression from the data refresh, not a rendering fault.

**Cause.** The strip is built from one day's board, and hides itself below four
settled picks (a loop that is mostly gap reads as broken). The page chose that
day as "yesterday, if anything finished on it, otherwise the newest day with any
result". Before the refresh the newest settled day was 29 September with 39
matches. The refresh loaded results up to 6 October, and 6 October had exactly
one finished match — so the page picked it, found one settled pick, and hid the
strip, while days with 32 and 22 matches sat two and four days earlier.

**Fix.** `GET /board/dates` takes `min_settled` and returns the most recent day
with at least that many finished football matches as `last_settled` (default 1,
the old meaning). The home page asks for 8 and uses yesterday only if it has that
many. Football only, because only football matches get a pick to grade. The strip
now reads "Last settled · Oct 4 · 9 of 9 came in": a day that can fill it, named
rather than passed off as last night. `tests/test_board_dates.py` pins the
threshold, that it is inclusive, that a day nothing meets gives no day rather
than a thin one, and that tennis and unfinished matches do not count.

**Two things worth knowing.**

- Rendering that day's board generates a pick for each match that has none, so
  the page stored 9 backtested predictions the first time it ran. It is the same
  side effect noted earlier (browsing the site grows the backtested record) and
  still needs a decision.
- After a change to a page's data calls, the dev server's `.next` cache kept
  serving the old render and masked the fix until it was cleared — the same
  trap recorded in the project notes.

## The scheduler made safe to switch on, and the daily refresh made correct

Still **off** (`ENABLE_SCHEDULER=false`) — turning it on remains the owner's call —
but it can now be turned on without either of the two ways it would have failed.

**1. The daily refresh was the root of the original staleness.** `refresh_data_job`
re-downloaded `E0` for season `2425` and nothing else: last season, one league. So
even a running scheduler would have left the whole domestic record frozen, which is
exactly how it went a year stale. It now pulls every league from the free source
for the current season (the 19 main leagues by season code, plus the 16 country
files by year), plus the previous season through July–September when a season's
last results are still arriving, then cleans and loads. None of it touches the
API quota, so it keeps the domestic record current on any plan. A failed download
or a down country skips that file and carries on. The league table
(`EXTRA_LEAGUES` in `scripts/fetch_extra_league.py`) is pinned by a test against
`clean_data.LEAGUE_NAMES`, so a league added to the pipeline and forgotten here
fails a test instead of silently stopping updating. Run for real end to end it
refreshed all 35 league codes, re-cleaned 118,007 rows, rebuilt Elo, and inserted
nothing new (nothing had been played since the morning's data). The old
`SCHEDULER_LEAGUE` / `SCHEDULER_SEASONS` settings are gone; `.env` still carries
them harmlessly (`extra="ignore"`).

**2. A quota guard.** Each API job now asks API-Football itself how much of the day
is left — its `/status` call is free and uncounted — and runs only if its worst-case
cost fits with a margin of 5 to spare. Asking the source means a script run by hand
or a second process cannot make it wrong, and there is no state to persist. It
fails closed: an unreadable status skips the job, because one missed run is cheap
and a spent quota is not.

**3. Right-sized cadence, by plan.** The old jobs would have spent far more than a
free plan's 100 a day. The free profile is worst-case 99: fixtures 3 runs × 3 days,
odds 2 × (9 + 10), results 4 × 3, stats 1 × 20, injuries 1 × 20 — and a test
computes that sum from the profile, so changing a cadence or a cap cannot silently
break the budget. A paid plan gets the original busier cadence and larger caps. Which
applies is read from the account's own daily limit (1,000 or more is paid), so
upgrading the plan changes behaviour with no edit; an unreadable status means free.

**4. The injury sync no longer loops over every team.** It covered all 3,467
(tennis players included) at two requests each, which alone would have spent the
quota at 03:30. It now covers only football teams with a fixture in the next three
days, soonest first, capped at 10 on the free plan.

Not done: the first request counted by the guard on subscription day still wants a
look at real numbers — the caps are worst cases, not measurements. 37 new tests in
`tests/test_scheduler_budget.py`; the guard's skip cases are seeded with real
fixtures so they cannot pass for want of anything to do.

## The scheduler turned on — and what its first run found

`ENABLE_SCHEDULER` is now `true` (in `.env`, which is not in git), and the backend
runs it: nine jobs, registered at startup. The first API job, fixtures, fired at
16:00 on the dot, looked three days ahead (three requests), and inserted 13 real
fixtures in modelled competitions. That is the first domestic fixtures the board
has held since the data went stale.

**It immediately found a real defect, which is what turning it on was for.** Of
the 9 clubs that run created, all 9 were clubs we already held under another
spelling — `Flamengo`/`Flamengo RJ`, `Botafogo`/`Botafogo RJ`, `HJK Helsinki`/`HJK`,
`CFR 1907 Cluj`/`CFR Cluj`, `Drogheda United`/`Drogheda`, `RB Bragantino`/`Bragantino`,
`Vasco DA Gama`/`Vasco`, `Universitatea Cluj`/`U. Cluj`, `Atletico Paranaense`/
`Athletico-PR`. A created club starts at the default rating, so each of those
fixtures would have been a coin-flip prediction on the board. It is exactly the
failure the club-ID mapping exists to prevent; the mapping had not been run for
these leagues (the free plan made it a deliberate wait), and the live feed cannot
tell the spellings apart without it. Fixed in four parts:

1. **Cleaned up.** `merge_team` (tested) folds a duplicate into the club it
   duplicates — matches, rating history and injuries re-pointed, the keeper learns
   the API id, the duplicate deleted — and refuses if the two carry *different* API
   ids (different clubs). The nine duplicates held no Elo history and no
   predictions, only their own fresh fixtures; each pair was checked by hand
   (same league, no conflicting id) and dry-run before the merge. Backup taken.
2. **Mapped the four leagues** involved (Brazil, Finland, Romania, Ireland) from
   their 2024 rosters, 4 requests: 19 of 20, 12 of 13, 16 of 20 and 11 of 11 clubs
   now carry API ids, so those leagues' next fixtures resolve by id. Clubs it would
   not guess at are in `data/processed/team_mapping_review.csv` (Atletico GO is
   the API's Atletico Goianiense; FC Voluntari and Metaloglobus are not in our data).
3. **A bug in the mapping tool, found by thinking about this case.** It selected
   a league's seasons with `label.startswith(str(year))`, which can never match a
   calendar-year league's stored label (`"2424"` for 2024), so it would have
   skipped Brazil, Finland and Ireland — precisely these leagues — and spent a
   request doing it. It now reads labels with `season_start_year`, skips a season
   it holds no matches for *before* spending a request, and `--ids` restricts it to
   named leagues.
4. **No longer silent.** The live loader now logs, by name and API id, every club it
   creates, with the command that maps it. Before, a duplicate club looked exactly
   like a new one.

**What this does not fix.** Only those four leagues are mapped. Every other league
the live feed covers (the European leagues above all, once their fixtures arrive)
will create duplicates of clubs with abbreviated Football-Data names until it is
mapped — Athletic Club versus Ath Bilbao is the textbook case. Mapping all of them
on the free plan is about 45 requests of the remaining day's quota. The instruction
on record is to run the full mapping the moment the plan is upgraded; until then the
new warning at least makes each duplicate visible, and `merge_team` removes it.

**Caveat on "on".** The scheduler lives inside the backend process, so it only runs
while the backend is running, and a missed run is not caught up. If the backend is
not up at 03:00 the refresh does not happen.

## Catch-up on startup, and the rest of the leagues mapped

Two follow-ups to turning the scheduler on, both at the owner's request.

**Catch-up on startup.** The scheduler lives inside the backend, and a cron run
missed while the backend is down is not made up, so a backend that is off at 03:00
means no refresh that night. On start it now checks how old the data is and, if
older than 20 hours, schedules the same refresh job 90 seconds later — after the
app is already serving, not during startup. Three decisions worth recording:

- *"Last refreshed" means a refresh that completed.* The job writes
  `data/processed/last_refresh.txt` as its very last step, after the load, so a
  refresh that dies halfway leaves the old marker and the data still reads as stale
  at the next start. With no marker it falls back to the processed file's age, so a
  database refreshed by hand is not refreshed again for nothing.
- *One refresh at a time.* The 03:00 run and the catch-up are the same job; each
  downloads, rewrites the processed file and rebuilds Elo. A non-blocking lock turns
  a second one away rather than queueing it behind the first, and is released if the
  job fails.
- *Twenty hours*, not a day: the nightly run keeps the data fresher than that, so a
  backend that has been up overnight never triggers it, and one started the next
  morning always does.

Verified for real: the processed file was backdated 30 hours, the backend restarted,
and it logged "Data is older than 20 hours … refreshing in 90 seconds", ran the job
at 17:45:55, refreshed 51 files (0 failed), rebuilt Elo and wrote the marker. It also
needs no API quota. 15 tests in `tests/test_scheduler_catch_up.py` pin the age
thresholds, that the marker is written only on completion, that a failed refresh
leaves the data reading as stale and releases the lock, and that two refreshes never
overlap (including a real second thread arriving mid-job).

**The rest of the leagues mapped.** The four leagues mapped after the first
scheduled run were not the only ones the live feed covers; every other league would
have created duplicates of clubs with abbreviated Football-Data names the moment its
fixtures arrived. The remaining 32 leagues were mapped from their 2024 rosters: 32
requests, leaving about 50 of the day's 100.

- 767 of 1,373 football clubs now carry an API id, and no id is shared by two clubs.
- **Spot-checked against independent evidence:** 15 well-known clubs' ids (Barcelona
  529, Real Madrid 541, Athletic Club 531, Manchester City 50, Bayern 157, Juventus
  496, …) all match what the mapping wrote. 15 of 15.
- The tool left 40 clubs for a person: names that share almost nothing, such as
  Wolves (our `Wolverhampton Wanderers`), Paris Saint Germain, most Chinese Super
  League clubs and the Dutch second-division sides. They are listed in
  `data/processed/team_mapping_review.csv`; the live feed's new warning will name any
  that still turn up as duplicates.

**Limits.** Only the free plan's 2024 season could be used, so a club promoted since
is on no 2024 roster and is still unmapped until the full mapping at subscription
(`--seasons 2016-2025`), and the current-season roster is not available on the free
plan at all.

## Every board price is filled — real where quoted, a flagged fair price elsewhere

**Why.** The board showed "–" in the 1/X/2 columns and under market picks (1X2, O/U,
BTTS) wherever no bookmaker price was stored. The owner wants a number in every cell.
This **supersedes the earlier principle** that the per-market columns show a real gap
where no price exists (only the best-tip column used a fallback).

**What changed** (`app/services/board_service.py`, `BoardTable.tsx`, `web/lib/board.ts`):
- A quoted bookmaker price always wins. Older rows keep 1X2 only in the legacy
  `odds_home_win/draw/away_win` columns; `effective_odds_markets` treats those as the
  real 1X2 line (the stored blob is never modified).
- Where nothing was quoted, the cell shows the pick's fair price, `100 / probability`,
  computed from the engine's own number and **flagged**: tips carry `odds_is_estimated`,
  the 1/X/2 cells carry the new row key `odds_estimated: {home, draw, away}`. The UI
  renders these as a dashed "≈" pill with a tooltip saying no bookmaker quoted it.
- Nothing is invented: a selection the engine gave no probability for stays empty, and
  the slip builder and bankers still read only real stored prices.

**Verified.** Across the 7-day window on the live API: 28 rows, 0 blank cells; in the
browser, 0 dash cells on Oct 4 with 26 "≈" pills. Real upcoming-fixture prices were also
fetched for all 13 upcoming fixtures with `scripts/fetch_odds.py --days 2`.

**Caveat.** A fair price is not a price anyone will pay — it has no bookmaker margin —
so "≈" numbers must never be read as value against the market.

## nerdytips.com re-crawled; the real-data gaps built, the rest listed with reasons

The owner asked for every page of the reference site to be visited and anything missing
replicated. The whole site was crawled again (nav, footer, 10 league landing pages, a
team page, a match page, the two market landing pages, a blog post, the content and
account pages, a language variant): 127 distinct links on the home page alone. The
audit against this project found these gaps that **can be built from real data**, and
they are built:

- **`/over-2-5-goals-predictions-today` and `/correct-score-predictions-today`**
  (`app/services/market_page_service.py`, `GET /markets/{kind}`). The day's fixtures
  ranked on one market, with that market's own 30-day record beside them, live and
  reconstructed counted apart. Over 2.5 is only a *call* where the engine leans over
  (so an under-leaning fixture is neither listed nor counted as a miss). Correct score
  is shown at its true hit rate — every settled call, 9 of 78 (11.5%) when built — and
  the recent-hits list says it is hits only. Prices are bookmaker where stored, else
  the flagged fair price; there is no stored correct-score line, so those are always ≈.
- **Team pages `/teams/[slug]`** (`app/services/team_page_service.py`,
  `GET /teams/{slug}`, `GET /teams`). Form, results from the team's own side, next
  fixtures, last-10 facts, season averages, and league position from our own results.
  Linked from the match header, league tables and a footer "Top-rated teams" column
  (ranked by engine Elo — not "popular", there is no traffic figure). TS and Python slug
  functions agree on all 1,373 team names. No squad, players or market value: none are
  ingested.
- **`/how-it-works`**, a "How to read the board" glossary under `/matches`, and a
  **Slip of the day** on `/bankers` (shown only for a card with matches still to play).
  The page deliberately omits the reference's claims about expected goals, odds
  movement and a "4 days before kick-off" window — this engine does none of those.
- **Slip builder fix:** `candidate_legs` skipped nothing, so a slip could contain a
  match already played. It now skips played fixtures. The slip service had no tests;
  `tests/test_slip_service.py` adds nine.

**Not built, and why** (each needs a decision or a source this project does not have):

- Log in / Register / Subscribe / Hit&Win: need auth (blocked on Supabase) and, for
  Subscribe, real plans and prices — the reference's are its own and must not be copied.
- Blog: needs a content process. Per-match previews could be generated from real
  numbers, but that is a product decision about auto-written prose.
- About / Contact / Privacy / Terms / Recommended sites: need the owner's real
  identity, contact address and legal text; a fabricated entity is exactly what the
  no-fabrication rule forbids. Recommended sites is an endorsement list for the owner.
- The 28 language versions: a translation project, not a template change.
- Reviews/Trustpilot strip, social links, app-store badges, "trusted by" logos: would
  all have to be invented.
- Players and squad value on team pages; the World Cup / Euro landing pages (those
  competitions are registered but disabled until the API plan covers them).

**Found while verifying (not caused by this work, not fixed here):** several board
requests at once can exhaust the backend's DB pool (5 + 10 overflow) because each
predicts and writes per request; SQLite lock timeouts then blank rows. And the
backend's rate limiter is 60 requests a minute per IP while the website is its only
client, so every visitor shares that budget. See the progress checkpoint.

## Design and copy pass: honest write-ups, contrast, mobile board

Run with the frontend and design skills (`frontend-design`, `design-taste-frontend`,
`better-interface`, `emil-design-eng`, `apple-design`, `find-animation-opportunities`).
`better-interface` delegates to six domain skills (`better-accessibility`, `better-layout`,
`better-writing`, `better-typography`, `better-colors`, `better-ui`) that are **not installed**
here, so those domains were not reviewed against their own rules; the checks below were done
directly (computed contrast ratios, a real keyboard-focus test, phone-width overflow checks).

**Copy.** Every visible write-up was rewritten for a professional register: consistent
"pick" terminology, no em-dashes in visible text, page titles use `|`, and the home FAQ now
has 13 answers (accuracy, publication timing, how to read a row, confidence, best tip,
bankers, coverage, profitability, betting advice, fixed matches). Two phrases borrowed from
the reference site ("We've got answers", "Got questions?") are gone, as are four decorative
eyebrow labels (three on the home page, one on the track-record FAQ).

**Accuracy fixes found while writing** (the old copy was wrong, not just clumsy):
- The FAQ said confidence is "out of 100"; the board shows it out of ten.
- It described the best tip as "furthest above its base rate"; the code picks the likeliest
  call among those that beat their base rate, else the likeliest overall.
- It said every pick is "published before kick-off and never altered"; neither is true.
  The reconstructed record is generated afterwards, and `_persist_prediction` overwrites the
  stored row on every recompute (a follow-up task was queued to freeze rows at kick-off).
  The track-record banner's "graded afterwards without being touched" was softened for the
  same reason.
- The hero led with the live 90.3% (31 picks) and hid the 1,999-pick backtest at 77.9%; it now
  states both, labelled, with "a small sample" while live picks number under 100. The home
  "About" tiles dropped their blended win-rate tile for the same reason.
- The slip page and the match page's market table quoted the -6.74% backtest as the engine's current return;
  the Analytics page rightly calls it an old single-league figure. All now say "last recorded".

**Design and accessibility.**
- Light-mode contrast: won `#0d8a63`→`#0a7553`, lost `#c7472e`→`#b03a24`, no-data glyph
  `#7c8898`→`#5f6b7c`, so small settled-pick text clears 4.5:1 on every surface; the
  "Scheduled" label uses the brighter gold. Dark mode already passed everywhere that matters.
- Phone board: the fixture column no longer soaks up the width below `sm`, so the 1/X/2 prices
  are in the first view, and the table has scroll-edge shadows (pure CSS) that show only where
  more columns are hidden.
- Date-strip and country links no longer prefetch: each prefetch ran the engine over a full day.
- Checked and left alone: the global focus ring (2px gold, verified on the league search box),
  reduced-motion handling, press feedback, and an absence of decorative animation.

**Motion.** None added. Frequency and purpose checks (find-animation-opportunities) leave the
board, nav and table without motion; the one orchestrated moment is the existing hero.

## The results strip, and a track-record scale bug found on the way

**Why the carousel kept vanishing.** The strip was built from "the last day with at least 8
finished matches", fetched as a full day's board with `.catch(() => null)`. Two structural
faults: this card is small (1 to 9 matches a day), so a qualifying day is rare and ages out of the
3-day window; and the board fetch recomputes a whole day's predictions, so under load it timed out
or failed and the strip silently disappeared. The earlier fix (`min_settled`) only widened the
threshold.

**The fix.** `GET /board/recent-settled` (`app/services/recent_results.py`) reads the newest graded
best tips straight from stored predictions: no recomputation, no day-size threshold, spans as many
days as it needs, and the strip prints the dates it covers. It cannot fail the way a live
prediction can, and a test asserts it never calls the predictor. Boards, league pages, the market
pages and the bankers/slip routes also now fall back to a stored prediction when a live one fails
(`predict_with_stored_fallback`), so a transient lock no longer blanks a whole card as "no
trained model".

**Track-record scale bug (the published record changed).** The `predictions` table stores 1X2 and
BTTS probabilities as fractions (0.62) and over/under, corners, cards and half-time lines as
percentages (62.0). `progress_service` read them raw, so match-result and BTTS calls sat on a scale
100 times smaller than every other market and could never lead: the record's "headline call" was
a goals, cards or double-chance pick wherever the board's best tip was a match result (0 match-result
headlines versus 91 of 300 once corrected). The test fixtures stored percentages, which hid it.
`stored_predictions.payload_from_stored` is now the single converter. Effect on the published
numbers: live 28 of 31 (90.3%) became 27 of 31 (87.1%); backtest 1,557 of 1,999 (77.9%) became
1,524 of 1,999 (76.2%); overall 78.1% became 76.4%. These are the honest figures for the picks
the board actually leads with.

**Still open** (separate tasks): the DB-pool pile-up under concurrent requests, and freezing a
stored prediction at kick-off.

## Home page: "Top leagues" and the illustrated "How our football predictions work"

Placed where the reference places them: **Top leagues** closes the picks section (under the
Yesterday/Today/Tomorrow boards, behind a divider, centred label, 5x2 grid of linked tiles);
the **three step cards** sit after the "what you get" section and before the FAQ, each an inset
16:9 diagram with a STEP badge above a title and two paragraphs.

Where this deliberately differs from the reference, and why:
- **Tiles are real, linked competitions only.** The reference's second row is Champions League,
  Europa League, Conference League, World Cup 2026 and Euro 2028. The UEFA club competitions are
  registered but disabled here (no data), so no tile is drawn for a page that does not exist. The
  grid keeps their slots: `components/home/TopLeagues.tsx` matches them by name, so the moment one
  is enabled and appears in `/leagues` it replaces a filler tile automatically. Today the fillers
  are Championship, Eredivisie and Primeira Liga; World Cup and Euros are real (history only).
  Labels say "World Cup" and "Euros", not "2026"/"2028", because the site holds past tournaments.
- **Flags, not league logos.** League emblems are licensed artwork with no source here; each tile
  uses its country flag (a globe for World/Europe) and a faint enlarged copy as the watermark.
- **Diagram 3 is not a neural network.** The reference draws one; this engine blends an Elo
  rating, a Poisson goal model and a gradient-boosted classifier, so the diagram shows three
  estimators merging into one probability and a graded pick. Diagrams and all text are original.
- Their copy about xG, injuries, weather and Java software is not claimed: none of it is done here.

**Home page rhythm.** Every home section after the first is now set off by a hairline and equal
spacing, applied once on the page container (`[&>section+section]` in `web/app/page.tsx`) rather than
per section, so a new section cannot drift out of step. The first sits under the results strip,
which has its own rule. The four "About" tiles are equal (253 x 153 px at desktop) and stretch from the
heading to the last line of the text beside them.

## SEO pass

Full plan, keyword map and launch checklist: [`docs/seo.md`](seo.md). Summary of what changed:

- **Crawlability:** `robots.txt`, `sitemap.xml` (about 1,100 URLs with real last-modified dates,
  fed by `GET /seo/urls`), and a staging safeguard: until `NEXT_PUBLIC_SITE_URL` is set the whole
  site is `noindex` and `robots.txt` disallows everything.
- **Per-page metadata** through one builder (`web/lib/seo.ts`): unique titles within about 62
  characters, descriptions within 155, canonicals, Open Graph and Twitter cards, a generated share
  image. Every page has one H1 that names what it is; the home H1 is now "Football predictions,
  every one graded".
- **Match pages** (the long tail, "X vs Y prediction") had one shared title and no H1; each now
  has its own title, description, H1, canonical on the readable URL, breadcrumb and `SportsEvent`.
- **Structured data:** Organization, WebSite, FAQPage, BreadcrumbList, SportsEvent and Dataset
  (the track record's two real CSVs), all describing visible content.
- **New page:** `/both-teams-to-score-predictions-today` (BTTS), same engine as the over 2.5 and
  correct-score pages. Over the 30 days checked its yes-leaning picks won 46.2% of 39, below the
  52.6% base rate; the page reports that as it stands.
- Thin team pages (under three recorded matches) are `noindex`.

**Launch blockers for ranking, not yet done:** About / Contact / Privacy / Terms /
responsible-gambling pages (need real details), analytics, and making the engine crawl-safe under
a burst of requests (queued as its own task).

## About, Contact and Privacy pages; the results strip made unable to vanish

**Pages** (`/about`, `/contact`, `/privacy`, linked from the footer and in the sitemap). They name no
person, company, address or founding story, because none is on record; the operator is shown only if
`NEXT_PUBLIC_OPERATOR_NAME` is set, and a public address only if `NEXT_PUBLIC_CONTACT_EMAIL` is.
- **About** states what the site is and is not, with live figures (graded picks, live picks,
  competitions, countries), the live/reconstructed split, data sources, a responsible-gambling
  section (18+, BeGambleAware and Gambling Therapy), and a dated **Corrections** list that already
  records the 7 October track-record fix and the rates it moved.
- **Contact** is a working form with no email address needed: the message is stored in
  `contact_messages` (migration `c8d9e0f1a2b3`, also created on first use) and read with
  `scripts/list_contact_messages.py` (`--done`, `--delete`). Defences: a hidden bot-trap field,
  3 messages per visitor and 60 site-wide per hour, hard length limits. No IP address or browser
  string is stored; the rate limit uses a daily-changing hash held in memory for an hour.
- **Privacy** was written from an audit of what the site really does: no accounts, no cookies (checked
  on the response headers), no ads, no analytics; the theme choice lives in `localStorage`; the only
  third-party request a browser makes is for country flags (flagcdn.com); the form stores topic,
  optional name, email and message only. **If analytics is ever added, update this page first.** It
  claims no compliance with any particular law; have a qualified person read it before launch.

**Why the carousel kept disappearing, and the guard against each cause.** It has vanished four times,
each for a different reason:
1. *It needed one busy day.* Fixed by reading the newest graded picks across days from stored
   predictions (`/board/recent-settled`).
2. *It shared a `Promise.all` with today's board*, so one failed board request threw the strip away
   even when its own request had succeeded. Fixed: the strip is fetched on its own, and every other
   section stands on its own request.
3. *A failed fetch was simply gone.* Fixed at three layers: the engine keeps its last good answer
   (120 s fresh, served stale if a recompute fails); the website keeps its own last good copy in
   memory and on disk, so it survives a web restart during an engine outage; and the strip's fetch
   never throws.
4. *Nothing bounded how long a request could hang* (a 3.6 minute page render was logged). Every
   engine call now has a timeout (45 s; 8 s for the strip).

Watching it: a backend job, `results_strip_canary`, rebuilds the strip's data every 5 minutes and logs an
ERROR if fewer than 4 graded picks exist or the rebuild fails. And `python scripts/check_site_health.py`
checks the engine endpoint and that the rendered home page actually contains the strip and populated
boards; it exits non-zero on failure so it can gate a deploy. **Run it after any change to the home page,
the engine's board routes or the database.** It was verified by killing the engine, wiping the website's
cache and restarting the website: the strip stayed.

## Renamed to SARDASPORTS

The site's name changed from UniquePredict to **SARDASPORTS** (owner's decision; the spelling was
confirmed against the GitHub repository `sardasports`). Everything a visitor or crawler sees was
renamed: the two-tone logo (white SARDA, gold SPORTS), page titles and descriptions, the share
image, structured data, the About, Contact and Privacy text, the FAQ, the footer, CSV download
filenames, the FastAPI title, the dashboard, the AI analyst's name and the knowledge-base text.

**Deliberately not renamed**, because doing so would break an existing database or setup for no
visible gain: the database file `data/uniquepredict.db`, the test database, the Docker/Postgres
credentials, the Python package name in `pyproject.toml`, the web server's temp-file name, and the
Wikipedia user-agent string. Older entries in this file keep the old name as history. The brand now
lives in one constant for the web app, `SITE_NAME` in `web/lib/site.ts`, and in the logo markup in
`web/app/layout.tsx`, `web/components/SiteFooter.tsx` and `web/app/opengraph-image.tsx`.

Also fixed on the way: `test_team_badges` demanded flags for the clubs on the board, which are
initials by design, so it passed or failed on whether the week's fixtures included internationals.
It now checks national-team fixtures only.

## Basketball and tennis on the site

The engine has priced NBA games and ATP/WTA matches for a while (see "Multi-sport" above), and
match pages for them worked, but nothing on the site led to them: no navigation, no sport pages,
no mention on the home page, nothing in the sitemap. This pass made them visible.

**What was built.**
- `GET /sports` and `GET /sports/{sport}` (`app/services/sport_service.py`, `app/api/routes_sports.py`):
  per sport, how many finished matches are on record and the date they run to, upcoming fixtures
  (whatever is really scheduled), the highest-rated competitors, the latest results with what the
  engine says about each, the competitions covered, and every model's accuracy beside the baseline it
  recorded. Cached for an hour, with the last good answer served if a recompute fails. A scheduler
  job (`sports_pages_warm`) keeps it warm, because pricing the latest tennis matches loads the whole
  history and takes about 15 seconds cold.
- Website: a sport switcher (Football / Basketball / Tennis) under the header on every page,
  `/basketball` and `/tennis` pages (`web/components/sport/`), a "Basketball and tennis predictions
  too" section on the home page, footer links, sitemap entries, a home FAQ answer, an About section,
  a How-it-works stage, and keyword-led titles and descriptions. Match pages for these sports now go
  "Back to tennis" and light the right tab, and show monogram badges instead of "?".

**What the pages say, and why.** They state the date the data ends and that no fixtures are loaded.
Today that is 16 Nov 2025 for tennis and 23 Jun 2025 for basketball. The "latest results" table is
labelled as reconstructed (the engine's output now, using only earlier results), not as published
picks, and the football record is never blended with them. The model table says "No measurable
edge" when the gap to the baseline is under two standard errors, which is how the tennis winner
model (+0.4 points on 13,734 matches) is reported: no better than picking the higher-rated player.

**Not done at the time of that pass (most of it is done in the section below).**
- *Live boards for today.* There is no fixture feed: tennis-data.co.uk publishes results and odds
  only, and the basketball plan serves past seasons. Fixtures need a source (a paid API-Basketball
  plan for the NBA; a schedule source for tennis, which is still unresolved).
- *Fresher data.* Both are months old. Tennis 2026 results can be fetched with
  `scripts/fetch_tennis.py --years 2026`, but `scripts/load_to_db.py` then has to rebuild Elo for
  every sport (it deletes and replays all of `elo_history`), which is slow and contends with the
  running engine, so it was not run unattended. After that the tennis models should be retrained.
- *A public record for these sports.* None exists: picks were never stored before kick-off. Once
  fixtures flow, store them the way football's are and grade them.
- *Per-player and per-team pages, league pages for the NBA, and a "today" board.* Each needs the
  fixture feed first.

## Basketball and tennis: every league, live, graded

The first pass made the two sports visible but static: results months old, no fixtures, the NBA
only. This pass made them live and wide.

**Basketball, every league the provider lists.** `ml/basketball_leagues.json` is the provider's own
list of 428 leagues (names, countries, women's competitions; league names shared by several
countries become "LNB (France)", "LNB (Chile)"). Two feeds fill the database
(`app/services/basketball_feed.py`):
- the *date feed*: `/games?date=D` for yesterday, today and tomorrow returns every league's games
  (80 to 140 a day) in one request. This is what makes a daily board possible on the free plan, and a
  league appears the day the provider starts listing it. Runs every 4 hours (3 requests);
- the *history backfill*: one request per league-season, 2022 to 2024 (all the free plan serves),
  best-known leagues first (`PRIORITY_IDS`), 551 league-seasons planned. It runs daily at 02:30
  with whatever quota the feed leaves (it keeps 25 back). 51 were fetched on 8 Oct 2026: 29,348 games,
  so the database now holds 36,064 finished games across 82 competitions and 1,660 teams.
The provider's limits shape this: 100 requests a day and **10 a minute** (requests are paced 6.5 s apart,
and a rate-limit answer waits a minute once). `/status` is asked first and nothing is spent if it
cannot be read.

**Models and measurement.** Winner: one LightGBM model over every league, retrained on 36k games:
66.1% on 7,012 held-out games against 57.1% for always picking the home side (NBA 66.0% against
54.7%; the page shows NBA and every other league separately). Totals: the three NBA models are
unchanged (their lines are NBA lines, and the trainer now filters to the NBA, which it did not need
to before). Every other league uses a normal distribution around the expected total with that
league's own running spread (`predict_basketball`, measured by
`ml/training/eval_basketball_statistical_totals.py`): 61.1% right at each league's average line
against 50.9% for the more common side, on 8,988 games across 20 competitions never used to fit it,
with calibration within a point or two at every band and still +2 to +3 points at lines six points
either side. That row is registered like a model (`statistical_basketball_totals`) so the page
shows it beside the others.

**Two kinds of "not enough".** A side with fewer than 6 prior games, or none for 800 days, is **not
priced** (a default rating is not evidence; without this an unknown team came out 79.5% to win).
A side whose newest game is over 300 days old is priced with its win probability pulled 20% towards
a coin flip and flagged ("ratings 16 months old"). The free plan cannot serve the 2025-26 season, so
today this affects most leagues. The pull factor (0.8) is a conservative choice, not a fitted one;
the record will show whether it is right.

**Tennis: the ATP and WTA tours, live.** tennis-data.co.uk 2026 was loaded (4,305 matches), the
current year's workbook is re-read daily, and ESPN's public scoreboard
(`app/services/tennis_feed.py`) adds fixtures and fresh results for the tournaments in progress,
qualifying included, every 30 minutes. **ESPN's feed is unofficial and unlicensed**: it can change
or vanish, and the owner should decide whether that is acceptable. The module is the only place
that knows about it. Singles only; retirements, walkovers and cancelled matches are left out
(as in the workbooks); names are matched to the history by surname and first initial; the
surface and the tournament name come from the history of the same tournament
(`ml/tennis_tournaments.json`), and an unknown tournament gets no surface rather than a guess.
When the workbook publishes a match ESPN already holds, that row is updated in place (so nothing is
counted twice and stored predictions keep pointing at it). `matches.tournament` is new
(migration `e0f1a2b3c4d5`) so a day groups by tournament. The tennis models were retrained: winner
64.8% against 64.5% for the higher-rated player (no measurable edge, as before); totals 59.8% and
65.1% against 55.2% and 55.8% on the 21.5 and 23.5 lines (clear edges).
**Not covered, and no free source found:** Challenger and ITF events, doubles. ESPN has no other tennis
feed (checked), and tennis-data has only the main tours.

**Stored in advance, graded.** `sport_predictions` (migration `d9e0f1a2b3c4`) holds one row per
match with percentages named `_pct`. `store_upcoming` writes predictions for the next 36 hours,
refreshes them while the match is more than 3 hours away and the row is over 6 hours old, then
leaves them alone; a side with too little history is never stored. `GET /sports/{sport}/board`
serves a day grouped by league or tournament with each prediction labelled stored, calculated or
reconstructed; `GET /sports/{sport}/record` grades the stored ones, live apart from reconstructed.
The record starts today, so it is small.

**Ratings.** `rebuild_elo_history` can now replay a single sport (the football replay takes minutes),
and it no longer writes the last sport's rating over every competitor's `teams.elo_rating`.
`app/services/elo_sync.py` continues from the last rating for new results and replays the sport only
when a result is older than ratings already written. The top-rated lists are now ranked within a
competition, because an ATP rating and a WTA rating, or an NBA rating and a Greek league rating, come
from different pools and were being compared.

**Speed.** Pricing tennis replayed the whole history into a rating table for every match (4 minutes
for 26 matches). The history index and the rating table are now built once per history and reused;
a board takes seconds. The pages are also warmed by the scheduler.

**Also done.** Terms of use page (a plain-language draft that names no country or company and needs
a qualified read). The share image uses the logo. SQLite write-ahead logging (`SQLITE_WAL`) and a
longer busy timeout, and then the whole of the DB-pool and freeze-at-kick-off work, were applied from
their worktrees with the owner's go-ahead (the sections below are those tasks' own write-ups). The
two overlapped in `prediction_service.py`: the freeze task's `_stored_payload` was renamed
`_published_payload` (a name clash), and the pool task's test that a result stamps the actual score on
the history was changed to the freeze rule (nothing reads that score, and a published prediction must
not be recomputed once the match has started). `_stored_is_current` also treats a kicked-off match's
row as current whatever happened since, or every view of a played match would recompute a number that
is never written back; the tests that needed a recompute now use tomorrow's fixtures.

**Still open.** Basketball: the remaining ~500 league-seasons arrive at about 50 a day; the 2025-26 season
and a higher request limit need a paid plan. Tennis: Challenger/ITF need a licensed feed.

## Serving a day's board cheaply and safely under concurrent requests

**The problem.** Every `/board` request recomputed every prediction (0.5–1.3 s per
fixture; a 32-match day ~16 s) and wrote a `Prediction` and a `PredictionHistory` row per
fixture. The home page asks for yesterday/today/tomorrow at once and Next prefetches, so
several boards ran side by side: the thread pool piled up, threads fought for SQLite's one
write lock (`database is locked`, each costing the 5 s busy timeout and then returning no
prediction for that fixture), connections ran out (`QueuePool limit … reached`), and
abandoned requests kept running after the browser gave up, so the backlog outlived the
burst. Reproduced on a copy of the live database with the unchanged code: 9 concurrent
requests (3 dates × 3), **none finished in 180 s**.

**What changed — no prediction says anything different** (verified, below).

1. **Stored predictions are served when still current** (`predict_for_matches(...,
   allow_stored=True)`). A football fixture's `Prediction` row is used instead of a
   recompute when all of these hold: its `model_version_id` is the active match-result
   model; it is not older than the newest of (a completed match before the cut-off
   changing, `EloHistory` being rebuilt, any active model being registered); and it is not
   older than the fixture's own last edit. The rule errs towards recomputing: an odds
   refresh or a stats fetch (both touch `matches.updated_at`) costs one recompute per
   fixture, never a stale number. A result arriving also forces one recompute, which is
   what stamps the actual score onto the prediction history, so that behaviour survives.
   Opt-in, default unchanged: the stored row has no per-estimator split, weights or
   explanation, so a payload from it simply lacks those keys (nothing is invented).
   `/board`, `/bankers`, `/slip` and a league page's fixtures opt in; `/predictions/today`
   (which reads the estimator split) and `/predict/{id}` keep recomputing.
2. **Writes are serialised and cannot lose a prediction.** `_persist_prediction` now takes a
   process-wide lock (including the "does a row exist?" check — unserialised, two requests
   both saw "no row" and the second hit `UNIQUE constraint failed: predictions.match_id`,
   a second failure mode the logs did not show), stamps `updated_at` explicitly (`onupdate`
   does not fire for an identical recomputation, which would leave a row forever "older"
   than the fixture), and if the write still fails it logs and returns the computed
   prediction instead of `None`. Serving a stored row writes nothing.
3. **SQLite runs in WAL mode with a 30 s busy timeout** (`SQLITE_WAL`,
   `SQLITE_BUSY_TIMEOUT_SECONDS`), so readers no longer block on a committing writer. WAL is
   a property of the file and persists once set; the backend converts the database on its
   first connection after the restart. **Backups:** copy the database with the backend
   stopped (a clean shutdown checkpoints and removes the `-wal`/`-shm` files) or with
   SQLite's backup API; copying only the `.db` of a running backend can miss recent writes.
4. **Identical requests share one computation** (`app/utils/coalesce.py`). `/board` and the
   `/bankers`/`/slip` day cache the finished payload for 30 s, concurrent identical requests
   wait for the one that is computing (waiters hold no database connection), at most two
   computations run at once, a failure is never cached and does not fail the waiters, and
   callers get deep copies. Abandoned requests now finish into the cache instead of
   repeating. The test suite clears these caches between tests.

**Verified live** (the worktree's code on port 8001 against a copy made with SQLite's backup
API; the real backend on :8000 was not touched):

| | original code | new code |
|---|---|---|
| 9 concurrent `/board` (3 dates × 3), cold | none finished in 180 s | all 200, 21 s wall, every fixture predicted |
| same, within the 30 s cache | — | 0.7 s |
| same, cache expired (stored rows served) | ~10–22 s per date, alone | 1.3 s |
| `database is locked` / `QueuePool` / `IntegrityError` in the log | — | 0 / 0 / 0 |

All three boards, `/bankers` and `/slip` were byte-identical to what the original code
produces one request at a time. 28 new tests in `tests/test_board_serving.py` (removing the
write lock makes the concurrency ones fail on the unique constraint).

**Not decided here.** Whether viewing a board should stop storing predictions for
already-played matches at all is still the owner's call; storing behaviour is unchanged,
only made safe. Note the stored-row path means repeated views no longer append a
`PredictionHistory` row each time (they used to, which made that table grow per page view);
a row is appended when a prediction is actually recomputed.

**Still open.** `market_base_rates` rescans ~118k matches on every uncached board (~0.5 s),
the floor under a cached-or-stored board. A same-day fixture's prediction depends slightly
on which fixtures share its batch (the history cut-off is the batch's earliest kick-off —
pre-existing), and a stored row keeps whichever batch wrote it. `/markets/{kind}` (in the
owner's uncommitted tree, not in this branch) calls `predict_for_matches` and reads only
`goals_markets` and `top_scorelines`, so it can pass `allow_stored=True` and wrap its day in
a `CoalescingCache` the same way.

## A prediction stored before kick-off is now immutable

**Why.** The track record (`progress_service._grade_all`, and `market_page_service._record`)
calls a prediction *live* when `Prediction.created_at < Match.match_date`. But
`_persist_prediction` overwrote every field of an existing row on each recompute while
leaving `created_at` alone, so a retrain, or any board/match-page view after the match,
could replace a published call and it would still count as live.

**What changed** (`app/services/prediction_service.py`):
- `_has_kicked_off(match)`: `status == "completed"` or `match_date <= now` (naive UTC, the
  same clock as `created_at`). Kick-off is a time, not only a status, because the fixture
  feed can lag.
- `_persist_prediction` no longer touches an existing row once the match has kicked off,
  and appends no `PredictionHistory` snapshot either. Before kick-off it upserts as
  before. A played match with no stored row still gets a backtest row (its `created_at`
  is after `match_date`, so it stays a backtest).
- `predict_for_match` serves the **stored** row for a started match instead of
  recomputing (`_stored_payload`). This is also cheaper: no history load, no model loads.
  The row never recorded `estimator_probs`, `model_weights_used`, `explanation` or whether
  the BTTS model was used, so those come back empty/`None` rather than re-derived from
  today's engine. `btts_model_used` is therefore `bool | None` in the schema and TS type.
  The first call that creates a backtest row still returns the full fresh payload.

**Other writers.** `Prediction(` is constructed only in `_persist_prediction`; scripts and
the scheduler write only `prediction_history.actual_*` (`ml/monitoring/evaluation.py`).
The history table is not the track record, but `ml/monitoring/calibration.py` does score
it, so a hindsight snapshot there would have double-counted a played match; none is
written any more.

**Not fixed.** Two simultaneous first requests for the same played match can both see no
row and race on the unique `match_id`. That predates this change. Rows already
overwritten before this fix cannot be recovered; their `created_at` is still before
kick-off, so they still read as live.

Tests: `tests/test_prediction_immutability.py`.

## Crawl safety: a search engine's first visit

Before inviting Google in, the site was crawled the way it will be: `scripts/crawl_test.py` fetches a
random sample of the sitemap's URLs a few at a time against a production build (`next build` and
`next start`; `next dev` compiles on demand and would measure the wrong thing) and reports failures,
the "engine is unreachable" banner on pages that returned 200, and timings.

**What it found (8 pages at a time).** 68 of 160 healthy. Two causes, one hiding the other:
1. **The engine's rate limit.** 60 requests a minute per address, and the engine's only client is the
   website's own server, so every request comes from one address: 209 of 458 requests were refused with
   429. The limit is now 6000 a minute (a ceiling against a runaway caller; abuse is limited at the
   website or CDN), in `config.py`, `.env.example` and the local `.env`.
2. **Repeated expensive work.** Every match page loaded the whole football history (about nine
   seconds, 118,000 rows) and refitted the Poisson baselines, and every league and market page graded
   every stored prediction (about four seconds). One Python process, so a few hundred pages meant
   an hour of queueing. Fixed by sharing, not by making any one thing faster:
   - the full history is loaded once and kept for ten minutes; windows are cut from it per day and
     shared (`HistoryWindow`), carrying the football fits built from them, so a match page costs
     about two seconds instead of ten; simultaneous cold requests wait for one load;
   - the graded list is kept for five minutes and shared;
   - `engine_warm` (every 4 minutes) refreshes both just before they lapse, so no visitor pays for a
     reload.
   A match's window is now cut at the start of its day, which is what the board already did (the
   earliest kick-off of the day), so a match page agrees with the board it came from.

**Result.** 200 of 200 healthy at 8 at a time, 1.4 pages a second (median 4 s, slowest 30 s), so the
whole sitemap (1,333 URLs) is about 16 minutes of crawling. At 4 at a time, which is closer to how
Googlebot behaves, every page was healthy even before these changes.

**What this does not do.** It does not make a single cold page fast: the first match page after a
restart still waits for the history load (the warm-up job runs 15 seconds after start). It
is one process, so a crawl still slows the site for visitors while it runs. For real traffic put a CDN
in front (cache the HTML for the public pages for a few minutes) and run more than one engine
worker; the caches here are per-process, so with several workers each warms its own.

## Checking the sport records, and the football quality items (10 Oct 2026)

**Basketball and tennis picks, two days in** (`python scripts/check_sport_record.py` prints this report
any time): 64 basketball and 56 tennis predictions stored before the match; 26 and 27 graded. Winner picks
14 of 26 (54%) and 16 of 27 (59%); totals 11 of 26 and 17 of 27. The 95% intervals are 35 to 71% and
41 to 75%: far too wide to say anything yet, and the report prints them so nobody reads more into the
percentages than the sample supports. Calibration buckets hold 3 to 11 results each. Re-run after a few
hundred results.

What the check found and fixed:
- **Awarded games were being stored as results.** 19 basketball games recorded 20-0 (a forfeit) were in the
  history, teaching the scoring averages and totals that a team can score nothing. The parser now refuses
  any game with a zero score; the 19 were deleted and basketball Elo replayed. (Retrain the basketball
  models at the next weekly run; the effect on 36,000 games is small.)
- **Matches that never reported a result stayed "In play" for ever** (a postponement the feed never
  mentioned). A match six hours past its start with no result is now "No result".
- Feeds were healthy: no errors, no duplicate fixtures (back-to-back games between the same two teams are
  real), no ties, no tennis result without sets.
- **Most basketball games are unpriced** (26 of 161 played in two days), because most leagues have no
  loaded history yet. That improves by itself as the nightly backfill proceeds; the report lists which
  leagues are unpriced.

**BTTS "below base rate" is not a bug.** Across 2,086 stored predictions the probabilities are calibrated
(predicted 50 to 60% came in at 53%, 40 to 50% at 50%) and the pick is right 53.1% of the time against
52.3% for always saying yes. The trained model's held-out test: 55.1% against 54.5% for the majority on
23,602 matches. So BTTS is nearly a coin flip with a very small real edge, not a broken model. The recent
live dip (10 of 27) is a short window: yes was only 42.6% of live results while the engine says yes
whenever it is above 50%. Nothing to fix in the model; the market page already reports its own record
beside the base rate.

**Unmapped clubs.** 425 of 1,404 football teams have no API-Football id (979 have one), 104 of them active in the last
400 days, and the well-known ones are naming differences (Paris SG / Paris Saint Germain, Sp Lisbon / Sporting CP,
Sheffield Weds / Sheffield Wednesday, OH Leuven / Oud-Heverlee Leuven). A partial mapping run (40
requests, 2024 rosters, which took the count from 828 to 979 mapped) wrote ids for 151 national sides and queued 53 clubs for review in
`data/processed/team_mapping_review.csv` without writing any weak match. The full run (2016 to 2025) is
still the first step of the subscription runbook above; guessing names here would risk wrong ids.

**The confidence score now spreads fixtures out.** The raw score (estimator agreement) was between 89 and
98 for nine fixtures in ten, so the board showed 9.1 beside 9.6. It carries a real signal (over 2,086
graded picks, the most agreed-on fifth won 81% against 72% for the least agreed-on fifth), so the board now
shows its **rank** among every stored football prediction, out of ten: 5 is typical, 9 or more is the top
tenth (`app/services/confidence_scale.py`). The order is exactly the raw score's order and it is not a
probability. With fewer than 300 stored predictions it falls back to the raw score over ten. Tennis and
basketball confidences are untouched. FAQ, glossary and the ring's tooltip say what it is now.

## Best tips: too many corners and cards (10 Oct 2026)

**Why.** The best tip is the likeliest call among those that beat their market's base rate by 5
points. Two flaws made corners and cards win it:
1. *One world-wide base rate for every league.* Over 8.5 corners lands about 64% of the time overall
   but 68% in the Championship; over 3.5 cards 58% overall but 75% in Serie B. Judged against the
   world's rate, every fixture in a corner-heavy or card-heavy league looked like a finding, and since
   the lines are ladders (over 7.5, 8.5, 9.5 corners; over 2.5, 3.5, 4.5 cards) there was always an
   easy, high-probability rung to take the headline. Measured on the 2,086 graded stored predictions,
   cards led 34% of best tips (Serie B 95%, La Liga 88%, Serie A 75%) and corners 15% (Championship 79%).
2. *The corner and card probabilities run high.* Corner calls claiming a 5-point lift realised 2.4
   (1,475 calls) and card calls claiming 6.8 realised 4.8 (1,140), while match-result, double-chance
   and goals calls realised what they claimed.

**What changed.**
- Base rates are measured per competition (`competition_base_rates`), falling back to the overall rate
  where a competition has under 150 matches recording the statistic. Every place that ranks calls now
  uses them: board, bankers and slip, league pages, market pages, the match page, the results strip and
  the track record.
- Corners need a 10-point lift and cards 8 to lead (`MARKET_MIN_HEADLINE_LIFT`); the per-market columns
  keep the ordinary 5. The evidence above is why, not taste.
- A competition that records no corners, cards or half-time goals gets no rates for them, so those calls
  are no longer made there (`STAT_MARKETS`). Major League Soccer has cards for one match in 4,850 yet was
  getting "Under 4.5 cards, 74%" as a best tip, from a model fitted on other leagues reading all-zero
  features. The match page now shows those lines as unavailable.

**Result on the same graded predictions.** Headline mix went from cards 34, goals 20, corners 15,
double chance 12, match result 12, BTTS 5 to match result 28, goals 24, double chance 17, cards 14,
corners 9, BTTS 7. Over the next four days' real fixtures: match result 33, goals 32, corners 10,
cards 10, double chance 9. Premier League corners 17% to 4%; Serie B cards 95% to 18%.

**The cost, stated plainly.** The published headline win rate falls from 76.2% to 68.9% (reconstructed
76.2% to 68.6%; live 77.8% over 54), because the picks removed were the easy high-probability lines.
It is the same engine, judged against a harder and more honest yardstick, and the figure on the home
page and track record moves with it automatically. The old number flattered the engine.

**Not done.** The corner and card probabilities themselves are about 5 points overconfident; the right
fix is calibrating those models, not just raising the bar.

## Calibrating the corner and card models (10 Oct 2026)

**Method.** `ml/training/calibrate_count_markets.py` replays `predict_match` over every match after
2024-09-14 (the active models' hold-out, so no probability was fitted on the match it is scored on),
sharded (`replay --shard k --of 6`, six processes, CSVs in `data/processed/calibration/`), then
`fit` fits a Platt curve per line, `p' = sigmoid(slope * logit(p) + intercept)`, on the first 60% by
date and scores it on the last 40%. A curve is registered as a `ModelVersion` row
`calibration_<market>_over_<line>` only if it improves held-out log loss by at least
`MIN_IMPROVEMENT` (0.0005).

**Result.** Corners over 7.5, 8.5 and 9.5 registered (slopes 0.91, 0.95, 0.88; intercepts -0.11,
-0.20, -0.18: all pull the probability down, i.e. the model was overconfident on the high side).
Cards did not earn a curve: 2.5 and 3.5 were already calibrated and 4.5 improved by less than the
threshold (that row is kept, inactive). Calibrated corners claiming a lift of 5 or more claim 6.7 and
realise 5.7; cards claim 6.9 and realise 8.5, i.e. cards were never the problem.

**Where it is applied.** At read time only, in `app/services/count_calibration.py`
(`calibrate_payload`), called on a freshly predicted payload, a published/stored payload and
`payload_from_stored`. The `predictions` rows are never rewritten, so a frozen pre-kick-off number
stays what the engine first said and nothing can be corrected twice. Curves are cached ten minutes;
`clear_cache()` after registering new ones. Tests: `tests/test_calibration.py`.

**Headline bars.** Re-measured with `scripts/measure_headline_mix.py` on 2,119 graded predictions.
Corners at 10 / cards at 8 stay: headlines won by corners fall from 68% to 61% if the corner bar is
lowered to 7.5, and card headlines win ~73% at any bar, so cards' bar is about variety (14.7% of
headlines at 8, 23% at 5), not accuracy. The comment on `MARKET_MIN_HEADLINE_LIFT` says so.

**Rerun when more data lands:** `replay` shards then `fit`, then restart the engine.

## Fixtures that never got a result (10 Oct 2026)

**Found.** 32 international fixtures from 28 Sep to 1 Oct (Nations League 16, friendlies 10, AFCON
qualifiers 6) were still `scheduled` nine days later, and so were never graded or fed back into Elo.
Two Irish Premier Division games from 9 Oct were waiting too.

**Cause.** Results come from API-Football by date, and a free plan only serves about the last three
days. The results job runs every six hours, but a cron run missed while the backend is down is not made
up, and (unlike the daily data refresh) the results job had no catch-up at startup. A fixture that
finished while the backend was off for more than three days could never be resulted again. The free
plan refuses the `ids` lookup too ("Free plans do not have access to the Ids parameter"), so the 32 old
ones cannot be fetched until the plan is upgraded.

**Fixed.**
- `app/scheduler.py`: `needs_results_catch_up()` is true when an API fixture kicked off more than three
  hours ago, within the last three days, and is still scheduled; if so `fetch_results_job` runs once, 150
  seconds after startup (`catch_up_fetch_results`).
- `scripts/fetch_results.py`: `resolve_stale_fixtures()` looks stale fixtures up by id (20 per request, at
  most 5 requests per run, up to 60 days back). `fetch_results_job` calls it on a paid plan only; on a
  free plan the refusal is logged and nothing more is spent.
- Tests in `tests/test_fetch_results.py` and `tests/test_scheduler_catch_up.py`.

**On upgrading.** The first results run after the upgrade settles the 32 international fixtures with no
action needed (5 requests). Nothing else in the upgrade runbook changes.

## Match-result accuracy: what was tried, and the one thing that helped (10 Oct 2026)

**Why.** The strip's 24 best tips read 16 won after reading 19 the day before. That was variance and a
sliding window (yesterday overall: 25 of 35, 71%; since 10 Sep: 113 of 159, 71%), but match-result
calls were the weak spot (Home/Away headlines win about 55%), so the result model was tested properly.

**Method.** `ml/training/replay_match_result.py` replays `predict_match` over the 25,075 completed
matches after 2024-09-14 (after the active models' training data, so no probability is scored on a
match it was fitted on), six shards, history cut at the start of each day, recording Elo, Poisson,
XGBoost and the blend. `scripts/analyse_match_result.py` scores them; anything fitted is fitted on the
earlier 60% by date and scored on the later 40%.

**Findings.**

| | log-loss | accuracy |
|---|---|---|
| Elo | 1.0241 | 48.99% |
| Poisson | 1.0411 | 47.97% |
| XGBoost | 1.0174 | 49.17% |
| current blend (.25/.35/.40) | 1.0181 | 49.29% |

- The blend is already at the level of its best part; three-way accuracy is about 49% (a pick that is
  never a draw wins 55% of the time on Home/Away headlines). That is the ceiling of this information.
- Retuned weights (0 / 0.15 / 0.85) gain 0.0006 log-loss and 0.1 points of accuracy: noise. Not applied.
- A separate correction per league did worse on the later 40% at every shrinkage tried. Not applied.
- The features the model could use (form over 5 and 10 matches, home/away form, rest days, congestion,
  head-to-head, Elo, league) are already all in; the gains left need information we do not have
  (bookmaker odds, confirmed line-ups, injuries at scale): see the API-Football upgrade plan.
- **One real fault:** the blend claims home wins 46.0% of the time and they happen 43.8%; it claims
  draws 24.1% and they happen 26.2%. Identical in every one of six periods. Cause: Poisson gives the
  home side 49.3% on average and Elo rarely leans to a draw (XGBoost alone is almost exact).

**Fixed.** One multinomial correction, `z = 1.064 * log(p) + [-0.091, +0.092, 0]`, fitted by
`ml/training/calibrate_match_result.py`, registered as `calibration_match_result`, applied at read time
beside the corner curves in `app/services/count_calibration.py` (stored rows are not rewritten). Held-out
log-loss 1.0186 to 1.0172; on the later 40% the average home claim goes from 46.0% to 43.7% (actual
43.8%) and the draw from 24.0% to 26.1% (actual 26.0%). Double chance and the match-result calls are
derived from those figures, so they follow. The more likely of home and away is unchanged in 96% of
matches.

**What it does not do.** It does not make the engine win more often: the headline win rate on 2,119
graded predictions is 68.3% before and 68.8% after, which is inside noise. It makes the percentages
honest, which also trims the Home calls that were being ranked on an inflated edge.

**Rerun when more data lands:** replay shards, `calibrate_match_result`, restart the engine.

## Strong tips: a higher win rate by putting forward what the engine is surest of (10 Oct 2026)

**The ask.** "I want a high percentage of won games in the best tips." The engine's accuracy cannot be
pushed much further with the data it has (see the match-result section above), but the *best tips* win
rate is mostly decided by which tips are put forward.

**Evidence.** On 2,117 graded best tips the stated probabilities are honest: tips claiming 70-80% won
75.9%, 80-90% won 85.8%, 90%+ won 95.6%. Winning more therefore means leading with the likelier tips.

| Best tips counted | Share of fixtures | Win rate |
|---|---|---|
| every fixture (unchanged) | 100% | 68.9% |
| rated 65%+ | 57% | 81.4% |
| rated 70%+ (**chosen**) | 51% | 83.6% |
| rated 75%+ | 45% | 84.4% |
| rated 80%+ | 32% | 88.1% |

Also measured and rejected: dropping the lift bars so the likeliest call always leads (83% on every fixture,
but 73% of the headlines become double chance and "under 4.5 cards", which win because they are nearly
always true, not because the engine saw anything).

**Built.** `ml/markets.STRONG_TIP_MIN_PROBABILITY = 70` / `is_strong_tip`.
- Every fixture keeps its best tip; each tip now carries `strong`, from the probability stored before
  kick-off, so it cannot be chosen after the result.
- The home results strip shows only strong tips (`/board/recent-settled` now returns `strong_only`,
  `min_probability`) and says so: "Recent strong tips ... 20 of 24".
- `/progress` gets `strong` (overall, live, backtest), shown as the first stat card on the track-record
  page and a line in the hero, always next to the all-tips records, which are unchanged and still shown.
- A gold star marks strong tips in the board's best-tip column.

**Result today.** Strong tips: 907 of 1,085 settled (83.6%); live (stored before kick-off) 49 of 56 (87.5%);
the strip 20 of 24. All tips together are still 68.9%.

**Honest limits.** Selecting by probability does not make the engine more accurate: the same tips win at the
same rate whether or not the others are shown. The strong record covers about half the fixtures. If a bar is
ever raised to chase a number, say so on the page: the record is only meaningful because the threshold was set
before looking at which tips won.

## Live scores for football (10 Oct 2026)

**The gap.** A football fixture had no in-play state: from kick-off until the by-date results job
saw it finished (every 6 hours on the free plan) it read as "not played".

**Source.** API-Football `/fixtures?live=all`: every fixture in play with its minute and score in a
single request (297 in play at the time of testing, on the free plan).

**Design.**
- Five new columns on `matches` (`live_status`, `live_minute`, `live_home`, `live_away`,
  `live_updated_at`; migration `a1b2c3d4e5f6`), **separate from `home_score`/`away_score`**. Those mean
  "the final result" everywhere (grading, Elo, history); a half-played 1-0 must never be mistaken for
  one. A live score is display-only, expires after 20 minutes without a refresh, and is ignored once
  the match is settled.
- `app/services/live_scores.py`: parse the feed, store the live view on fixtures we already hold
  (matched by `apif-{id}`, never creating one), clear it when a fixture drops out of the feed, and
  settle any fixture the feed reports as just finished.
- `fetch_live_job` (id `fetch_live`): skipped without spending a request when no fixture kicked off
  within the last 3 hours; on the **free plan** every 30 minutes and only while at least 40 requests of
  the day remain (so it can never starve the fixtures, odds and results jobs); on a **paid plan** every
  2 minutes with no reserve. The plan is read from the account, so upgrading changes it by itself.
- Board rows carry `live` (`label` "63'" or "HT", `home`, `away`) while `score` stays null and
  `status` stays "scheduled"; `/predict/{id}` carries it too. The board shows `LIVE 63'` and the score
  in red beside the names; the match page header shows the score and `Live 63'`.

**Checked against the real feed.** 147 fixtures in play, 18 to 20 of them in our database; their
final-score columns stayed empty and the board and match page showed minute and score.

**Limits.** On the free plan updates are at best every 30 minutes and are often skipped by the
reserve rule, so it is "live-ish" until the plan is upgraded. The pages are server-rendered and the
site caches engine data for 1 to 3 minutes, so the screen can trail the engine by that much; a
client-side refresh of in-play rows is the next step if exact timing matters. Only competitions this
engine already ingests have fixtures to decorate (other leagues in the feed are ignored).

## Speed, phone layout and the best-tip display (10 Oct 2026)

**What was reported.** The site felt slow; pages scrolled sideways on a phone; the Today board
read "43/97 best tips won"; Under 2.5 lost a lot and only Under 3.5 should show.

**Slow.** Measured through the temporary address: even `/robots.txt` took about 0.8 s, so most of
a page's time is the quick tunnel's network path, not the engine (a warm board is built in about
1 s). Three real causes were found and fixed:
- *Elo rebuild.* Every batch of new results triggered `rebuild_elo_history`, which deletes and
  re-inserts about 236,000 rows in one transaction and holds the database write lock for minutes.
  With the new startup results catch-up this happened right after every restart, exactly when the
  first visitors arrived (a warm-up that should take 30 s took 14 minutes). Football now uses the
  existing incremental `sync_elo`, extended with the per-competition K, and its safety check is
  per team instead of global. Verified equal to a full replay (`tests/test_elo_sync_football.py`).
  The results job went from 14 minutes to 14 seconds.
- *Cold boards.* `engine_warm` now also builds yesterday's, today's and tomorrow's boards every
  4 minutes, under the same cache key a request uses.
- *Rebuilds under contention.* The engine's board cache serves an entry that has just expired
  at once (up to 10 minutes past its 30 s life) while one background rebuild replaces it
  (`CoalescingCache(stale_seconds=...)`); a request that landed on a rebuild during a busy
  moment used to wait 40 seconds. Sampled every 12 s for 5 minutes after a restart: 0.23 to 1.4 s.
- *Edge caching, for when there is a domain.* Public pages now send
  `Cache-Control: public, s-maxage=60, stale-while-revalidate=600` (not `/api`, `/_next`, CSV).
  Cloudflare does not cache HTML by itself: add the Cache Rule in `docs/deployment.md`.

**Phone.** Two page-wide overflows, both found by measuring `scrollWidth` on every route at 375 px:
the 1 px `.sr-only` labels in the board table were absolutely positioned outside the scroller and
stretched the page to 725 px (`.overflow-x-auto { position: relative }` in `globals.css`), and the
track record's chart grid and the prediction rows had no `min-w-0` / stacking below `sm`.

**Under 2.5.** As a best tip it won 56.7% of the time (180 tips) against 68.7% for all tips, while
Under 3.5 won 85.3%. `goals:under_1.5` and `goals:under_2.5` are now in `HEADLINE_EXCLUDED`: they are
still priced and listed on the match page, they just do not lead a row or a goals column. The record
did not move (68.3% against 68.7%; strong tips 83.5% either way).

**"43/97".** The day tile now reads "Strong tips won" (tips rated 70%+ before kick-off) with the
all-tips figure in its note, the same framing as the home hero and the track record
(`counts.strong_finished` / `counts.strong_won`).

## A Dixon-Coles goals model, and what it did and did not change (10 Oct 2026)

**The ask.** "Add the Poisson model with a Dixon-Coles adjustment" to lift the best tips to about 70%.

**Built.** `ml/poisson/model.py` `DixonColesModel`, now the full-time goals model
(`ml/prediction/predict.fit_goals_model`, `GOALS_DECAY_PER_DAY = 0.001`):
1. *No second home-advantage factor.* `PoissonModel` multiplies the home side's goals by 1.15 on top
   of a league average of home goals that already contains the home advantage. Counted twice it
   claimed home wins 48.5% of the time against 42.5% real. This was the largest single fault.
2. *The Dixon-Coles low-score correction* (`rho`, about -0.045, estimated by maximum likelihood).
3. *Recency weighting* (`exp(-0.001 * age_in_days)`, a half-life of about two years).
The count-stat models (corners, cards, half-time goals) still use the plain `PoissonModel` with its
1.15, so their registered corner curves are untouched (a test pins both defaults).

**Chosen on evidence, out of sample** (`scripts/evaluate_goal_models.py`, 2,636 held-out matches,
history cut at the start of each day):

| goals model | 1X2 log-loss | over 1.5 | over 2.5 | over 3.5 | BTTS |
|---|---|---|---|---|---|
| plain Poisson (before) | 1.0533 | 0.5573 | 0.6880 | 0.6011 | 0.6922 |
| no double home advantage | 1.0447 | 0.5562 | 0.6869 | 0.5987 | 0.6940 |
| + Dixon-Coles | 1.0444 | 0.5560 | 0.6869 | 0.5987 | 0.6935 |
| + decay 0.001 (**used**) | 1.0335 | 0.5547 | 0.6846 | 0.5959 | 0.6931 |
| + decay 0.002 | 1.0316 | 0.5568 | 0.6877 | 0.5977 | 0.6957 |
| + decay 0.005 | 1.0368 | 0.5645 | 0.6991 | 0.6038 | 0.7031 |

**The blend** (`replay_match_result`, all 25,181 held-out matches): the goals model alone went from
1.0411 to 1.0250 and now claims home 43.6% (real 43.8%), but the three-estimator blend only from
1.0181 to 1.0161 because XGBoost was already doing most of the work; three-way accuracy is 49.3%
either way. The blend is now calibrated by the model itself (home 44.0% against 43.8%), so the
match-result correction added earlier no longer helps (1.0171 to 1.0167, below its threshold) and
**has been cleared**: it was fitted to the old, biased blend and would now over-correct. Retuned blend
weights again did not help. After deploying, run once on each database that has the old correction:
`python -m ml.training.calibrate_match_result --clear`.

**The number that matters** (`scripts/evaluate_best_tips.py`: the whole engine, old goals model with
its correction against the new one, the same 8,433 held-out matches, production tip rules):

| | all best tips won | strong tips (70%+) won |
|---|---|---|
| old goals model | 66.7% | 80.3% |
| Dixon-Coles | 67.0% | 80.2% |

So this is a better-calibrated model and a cleaner one (it replaced a patch), **not** a jump in the
win rate. The best-tip win rate is set by which tips are put forward: over the new engine's tips,
claim >= 50% wins 72.6% (82% of fixtures), >= 60% wins 77.4% (66%), >= 70% wins 80.2% (55%), >= 80%
wins 86.0% (22%). The stated probabilities are honest at every level (a tip claiming 76% won 76.5%).

**Legacy rows.** Predictions stored before this change were made by the old engine and are now read
without a correction, so their home probability reads up to two points high; new ones are right.

## Corners and cards out of the best tip; draw no bet in (11 Oct 2026)

**The ask.** No corners or cards as the best tip, other markets in, and add draw no bet (DNB).

**Built.**
- `ml/markets.HEADLINE_EXCLUDED_MARKETS = {corners, cards}`: they are never *the* best tip and a fixture
  with nothing else has none. They are still priced, still listed per market on the match page and
  still graded in the market breakdown. The lift bars that used to hold them back
  (`MARKET_MIN_HEADLINE_LIFT`) are gone; they had no remaining job.
- `DNB` market (`dnb:home`, `dnb:away`, shorthand "1 DNB" / "2 DNB"): the probability is home / (home +
  away), i.e. the chance a side wins given that someone does; derived from the match-result
  probabilities, so it cannot disagree with them. Judged against the base rate of the same
  conditional (`app/services/base_rates.py`). No bookmaker DNB price is stored, so it shows its own
  fair price, flagged as an estimate.
- Grading: a draw returns the stake, so it settles **void**, not lost, and (like an unrecorded
  statistic) is kept out of the win rate and reported separately. The day tile, the strip, the track
  record and the strong-tip record all count only won and lost; `counts.settled` carries that
  denominator.
- Copy updated (FAQ, how it works, glossary with a DNB entry, About corrections).

**Measured on 2,225 graded predictions (same fixtures, the three rule sets):**

| | won of settled | refunded draws | strong tips (70%+) won |
|---|---|---|---|
| before (corners and cards allowed) | 68.0% | 1.4% | 83.4% |
| corners and cards out | 65.8% | 0% | 80.8% |
| corners and cards out, DNB added | **72.7%** | 12.2% | 80.9% |

Taking corners and cards out costs about 2 points (card tips, in particular, won 73 to 75% of the
time). DNB more than recovers it, and it also leaves fewer outright losses: a draw that used to
lose a Home pick is now a refund. Of every 100 best tips, about 64 win, 24 lose and 12 are refunded.

**What to know.** DNB becomes about half of the best tips (49% of the sample; the straight match-result
pick almost disappears, because "home given a winner" is always likelier than "home wins"). It is
the right comparison for what a bettor gets, but it is a different bet from a straight win, and the
win rate is of tips that were settled. If DNB should not crowd out straight picks, a higher bar for it
(as double chance has) is a one-line change in `ml/markets.py`.

## Basketball and tennis: every market that can be priced honestly (11 Oct 2026)

**The ask.** Over/under for each quarter, each half, full time and each team; and for tennis, the
many markets beyond a winner. Not just home win or away win.

**What decides whether a market can exist.** It must be priceable from, and gradable against, real
period results. So the first step was data: `matches.period_scores` (migration `b2c3d4e5f6a7`,
`ml/period_scores.py`), filled by `scripts/backfill_period_scores.py` from files already on disk (no
API requests): quarter scores for 35,866 basketball games (99.9% of those finished; quarters plus
overtime equal the final score in all of them) and set-by-set games for 80,130 tennis matches (42
rows whose sets contradicted the recorded result were dropped). The live feeds (API-Basketball, ESPN)
now store the same detail going forward.

**Basketball** (`ml/basketball_markets.py`, profiles in `ml/basketball_period_profiles.json`, fitted
and evaluated by `scripts/fit_basketball_period_profiles.py`): home and away team totals, 1st and 2nd
half totals and winners, each quarter's total and winner, and the full-game spread (overtime included),
in addition to the existing game total. Three over/under lines per market (always x.5), derived from
the engine's expected points for each side and the league's own period shares and spread. A league's
format is read from the data: 12,124 games (NCAA) are recorded in two halves, so they get halves
and never a "quarter 1". Winner markets include the tie probability (a tie is a real outcome in a
quarter) and follow the moneyline. **Out of sample (7,578 games after Sep 2024):** claimed 33% / 50% /
67% happened 31-32% / 50% / 66-68% for totals, team totals and the spread; period winners claimed
79-80% happened 76% (a fitted shrink, slope 0.88, brought them within 1 to 3 points).

**Tennis** (`ml/tennis_markets.py`, parameters in `ml/tennis_market_params.json`, fitted and
evaluated by `scripts/fit_tennis_markets.py` on 72,598 matches): correct score in sets (3 or 5 set
format), total sets, set handicap, home/away player to win at least one set, first set winner,
first set total games, game handicap, and tiebreak in the match; total games keeps its trained model.
Everything is built conditional on who wins, so the home set scores sum exactly to the match win
probability. **Out of sample (13,154 matches since Jan 2024):** set markets within 1 to 2 points at
every band (e.g. a claimed 70% to win a set happened 71%, straight-sets scores 26%->26%, 14%->15%),
first set winner 67->66, game handicap 34->32 and 66->68, tiebreak 29->31, 45->48; the weakest is
total sets over (claimed 54% happened 58%, n=1,216).

**Honesty notes.** Every one of these is `source: "statistical"`: a distribution around an
expectation with measured spread, not a model trained per line, and the board says so. The tennis
calibrations were fitted on Elo-only probabilities, so they are if anything slightly conservative for
the live Elo+model blend. Predictions stored before this change carry no markets (they were not priced
then); new ones do, and a day with no stored rows shows them freshly calculated.

**Where it shows.** Each match on the basketball and tennis boards has an "All markets" panel with
every line's probability and, once the match is over, a tick on the side that came in. The sport
page's record section adds a per-market accuracy table (the call nearest a coin flip on each market,
stored-in-advance kept apart from reconstructed).

**To deploy.** `git pull`, rebuild, then once on the server:
`alembic upgrade head` and `python -m scripts.backfill_period_scores` (both inside the api container).
The image also needed `openpyxl` (it reads the tennis workbooks, was missing from the lockfile, so the
server's tennis workbook refresh could not have run): installed in `docker/Dockerfile.api`; run
`uv lock` when convenient and drop that line.

## Basketball and tennis list only matches that have a prediction (11 Oct 2026)

A side with too little history is not priced (`thin_history`), and the board used to list those
matches anyway with "Not enough history". On a typical day that was most of the basketball board
(for 10 Oct 142 of 160 rows, in 61 competitions) and about half of tennis. They are now left off
everywhere: the day board (`build_board`, so a league with nothing priced disappears too), the
"upcoming" and "recent" lists on each sport page (`sport_service`, which over-fetches so the list
still fills), and the home page's "upcoming" count, which now counts only fixtures carrying a stored
prediction. The engine's coin-flip numbers for thin matches are discarded rather than shown as picks.
Football is unchanged (its board still shows a fixture without a prediction, as stated in
how-it-works). A match is still reachable by its own URL; it is just not listed.

## Club crests beside every team, flags beside every country (11 Oct 2026)

Football clubs now show their real crest. The data already held the provider's team id for
1,019 of 1,426 clubs (the old note that one in 880 had one was out of date), and the provider's
media server serves a crest per id without a key, so the engine builds the URL from the id and
nothing is stored or downloaded (`ml/team_badges.py`: `crest_url`, badge kind `crest`, with the
initials kept so a crest that fails to load falls back to the monogram in the browser,
`web/components/board/CrestImage.tsx`). It reaches every board, league and market page through
`build_row`, the match page and team pages, and the footer's "Top-rated teams" and "Top leagues"
lists, which also gained crests and flags. The leagues page's "Most match history" tiles gained
flags; the country sidebar, directory and league pages already had them.

**Coverage.** 813 of the 902 clubs active in the last 13 months have a crest (90%). The 89 without
carry the football-data.co.uk spelling ("Paris SG", "Sp Lisbon", "Sheffield Weds"), which `--map-teams`
pairs to a provider id by roster; they keep the initials until that has been run. A club is never
given a crest by resemblance of name.

**Not covered.** Basketball teams and tennis players: there is no crest or country field for them in
the data, and inventing one would put a wrong badge beside a name. **Rights:** club crests are the
clubs' trademarks; the images are the provider's, loaded from its server for use alongside its data.
Confirm the provider's terms cover a public site before launch.

## Interface revamp to the client's mock-up (12 Oct 2026)

**What changed.** The look follows the supplied home-page mock-up: near-black ground (`#06090f`),
one bright yellow (`#f5c000` / `#ffd43b`), squared uppercase buttons, yellow-framed panels. Dark is
now the default theme for a first-time visitor whatever their system prefers (the toggle and a
stored choice still win). The tokens are in `app/globals.css`, so every page inherits them.

**Home page, top to bottom** (`app/page.tsx`): `HomeHero` (wordmark, claim, two buttons, drawn
football/basketball/tennis picture in `HeroArt`), `FeatureStrip` (five promises), `FeaturedPredictions`
(the engine's most likely picks still to play: two football, one basketball, one tennis, from
`lib/featured.ts`), `BrowseSports`, `RecordPanel`, `LatestResults` with "Why you can trust it", and
then the existing day boards, leagues, how-it-works and FAQ. The header has a yellow active-page pill
(`NavLinks`) and a "Today's picks" button; the footer gained an 18+ "Play responsibly" bar.

**Deliberately not copied from the mock-up, because there is nothing real behind it:**
- Premium plans and prices, "Join Premium", Login and Join Now: the site is free and has no accounts.
  The framed panel holds the record instead.
- "What our members say": no member reviews exist and none are invented. The space says why the
  record can be believed (picks saved before kick-off, losses stay, live and rebuilt kept apart).
- American football / NFL: not covered. The tile reads "More sports, coming soon" and is not a link.
- Photographed athletes and a "Bet smart" slogan: no rights to the photographs, and this site gives
  probabilities, not betting advice. The picture is drawn.
- Blog, Live Scores page, Statistics page, search box: these pages/features do not exist.

**Featured cards** show only matches still to play, so a card is never a result. Basketball had no
priced game on the day this was built (the NBA season starts later in October), so that card is absent
rather than filled; the row simply has three cards.

## The API plan upgraded to Pro: crests for every club, live matches, fast settlement (12 Oct 2026)

Plan read from the account's own `/status`: **Pro, 7,500 requests a day**. The scheduler's paid
profile switched on by itself (it reads the limit), and three things were built on it.

**Club ids and crests.** `fetch_api_competitions --map-teams --seasons 2016-2025` used 323 requests
and lifted football clubs with a provider id from 1,019 to 1,329 of 1,426. 34 more were set by hand
where the provider's roster still carries a club's former name (the Chinese Super League mostly),
each checked against its roster or a search result. **Every one of the 1,361 ids was then audited:**
the provider's own name for each id was fetched (`data/processed/team_id_audit.csv`) and compared with
ours. That audit found, and fixed, three wrong ones the mapping had produced: Paris SG had been paired
with Paris FC (114; Paris Saint-Germain is 85), and Guangzhou FC / Cangzhou had taken the ids of
Guangzhou R&F and Hangzhou Greentown. The remaining 50 spelling differences were read by eye and are all
the same club. 860 of the 902 clubs active in the last 13 months had a crest before the by-hand pass;
now 99%. The ids travel as `ml/team_api_ids.csv` (`scripts/team_api_ids.py export|apply`), which only
ever fills a gap and reports a conflict instead of overwriting.
Why the audit matters: a one-to-one pairing is right almost always, and a wrong crest beside a team is
a factual error; the provider's name for the id is the only check that does not trust the pairing.

**Live matches.** `/board/live` and a `/live` page (refreshes every 20 seconds while open), plus a
"Live now" band on the home page that exists only while something is in play. Paid cadence is a poll
every 2 minutes.

**Settled within a poll of full time.** The live feed lists only matches in play, so a match that ends
just vanishes from it. On a paid plan each poll now looks up, by id, every fixture that dropped out of
the feed or kicked off long enough ago to be over (`ended_candidates`, 20 ids per request), and settles
it there and then, with Elo. The by-date results job runs every 15 minutes instead of every 3 hours.
A free plan never makes the by-id lookup (it would be refused).

**Not done yet, and why.** The lower divisions, domestic cups, UEFA competitions and the extra
internationals (runbook steps 2 to 5 above): the data pull is one run (1,248 requests of history,
650 for 2022-2026), but turning those competitions on widens the models' feature vector, so it needs
the 12 football models retrained and checked against the current ones before it goes anywhere near the
live site. That is its own piece of work and was not started without a go-ahead.

## Accounts, admin dashboard and premium plan (14 Oct 2026)

Built from the plan in `docs/plan-accounts-and-premium.md`, using the recommended defaults where
the owner had not yet decided, and self-hosted accounts because no Supabase credentials exist.

**Accounts** (`app/services/auth_service.py`, `/auth/*`, pages `/signup`, `/login`,
`/verify-email`, `/forgot-password`, `/reset-password`, `/account`): sign-up needs a confirmed
18+ box and accepted Terms, both stored with a date; the e-mail address must be confirmed before
sign-in; reset and change password; "sign out everywhere"; the member can delete their own account
with their password. Passwords are salted scrypt (standard library, no new dependency). Sessions
and e-mail tokens are stored only as SHA-256 hashes, single use, expiring. Sign-up, sign-in and
reset are rate-limited. Registering a known address and asking to reset an unknown one answer
exactly as the normal case does, so addresses cannot be discovered.

**Admin dashboard** (`/admin/*`, role `admin`, created with `scripts/create_admin.py`): overview
with what still needs setting up; **picks** (write, save as draft, publish, delete, settle as won,
lost or void with a reason); **blog** (Markdown editor with live preview, publish, unpublish,
delete, premium-only); **members** (search, give or end premium, delete); **premium plans**; the
**mail outbox** (every e-mail is written there first, so until SMTP is set the owner can read and
pass on a confirmation link); and an **audit log** of every change.

**Integrity rules** (tested): a published pick is never edited; it can be deleted only until its
match kicks off, after which it stays on the record and can only be settled or voided with a
reason. A premium pick is hidden from non-members only until kick-off. A premium post's summary
is never copied from its body.

**Premium** (`app/services/premium_service.py`, `payments.py`, `/premium`): one payment buys one
period, with no automatic renewal. Stripe Checkout and Paystack are implemented against signed
notifications (signature verified, each event applied once, amount checked against the plan). Both
are untested against the real providers: they need test keys, which do not exist yet. **No plan or
price is pre-filled**; the owner sets them in `/admin/premium`.

**Changed on the way:** the Privacy and Terms pages said "no accounts, no cookies"; they now
describe accounts, the one session cookie, payments, e-mail and the club-crest image server.
Dark-theme header gained a compact account control; the blog, picks and premium pages were added
to the sitemap.

**Not built (still on the plan):** e-mail digests and Telegram alerts, member dashboards (watchlist,
saved slips), automatic renewal and reminders, per-provider refunds from the dashboard, a member
export. Say which next.
