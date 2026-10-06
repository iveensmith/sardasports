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
  the 90-minute score, which is what 1X2 is about, was 2–2. About one cup tie
  in six goes beyond 90 minutes (22 of 126 in Copa del Rey 2024) and every one
  is level at 90, so using `goals` would have mislabelled the 1X2 outcome of
  all of them. `score.fulltime` is used.
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
