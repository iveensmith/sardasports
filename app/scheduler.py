"""APScheduler automation — Step 12 of the spec.

Wires the existing, already-tested scripts and training functions into
scheduled jobs. Nothing here duplicates logic — every job calls straight
into `scripts/*` or `ml.training.*`/`ml.monitoring.*`, so "what does the
daily job actually do" always has one place to look.

Started from `app.main` on FastAPI startup, guarded by `settings.enable_scheduler`
(default off) so tests and one-off script runs never accidentally start
background jobs.
"""

from __future__ import annotations

import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database.session import SessionLocal
from app.services.api_budget import MARGIN, PAID_DAILY_LIMIT, api_status, is_paid_plan
from app.utils.config import get_settings
from app.utils.logging import get_logger
from app.utils.seasons import season_codes_to_refresh

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None

# Written at the very end of a refresh that completed. It is the scheduler's only
# memory of when the data was last brought up to date: a refresh that fails
# halfway leaves it alone, so the next start sees stale data and tries again.
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
LAST_REFRESH_MARKER = PROCESSED_DIR / "last_refresh.txt"

# The scheduler lives inside the backend, and a cron job missed while the backend
# was down is not made up. So on start it looks at how old the data is and, if it
# is older than this, runs the refresh itself — shortly after startup, not during
# it, so the app is already serving. A little under a day: the nightly run keeps
# the data fresher than this, so a backend that has been up overnight never
# triggers it, and one started the next morning always does.
CATCH_UP_AFTER_HOURS = 20
CATCH_UP_DELAY_SECONDS = 90

# How often the basketball and tennis pages' data is rebuilt ahead of visitors.
SPORTS_WARM_MINUTES = 4

# One refresh at a time. The catch-up and the 03:00 run are the same job and must
# never overlap: each downloads, rewrites the processed file and rebuilds Elo.
_refresh_lock = threading.Lock()


def hours_since_refresh(now: datetime | None = None) -> float | None:
    """Hours since the last refresh that completed, or None if there never was one.

    Falls back to the processed file's age when there is no marker yet, so a
    database that was refreshed by hand before the marker existed is not
    refreshed again for nothing.
    """
    now = now or datetime.now()
    for path in (LAST_REFRESH_MARKER, PROCESSED_DIR / "matches.csv"):
        if path.exists():
            return (now - datetime.fromtimestamp(path.stat().st_mtime)).total_seconds() / 3600
    return None


# The results job asks API-Football for the last few days by date, and a free plan cannot ask
# further back. A cron run missed while the backend was down is not made up, so a fixture that
# finished in that gap stayed "scheduled" for good (32 international fixtures did). So on start
# the job also runs once, shortly after, if any fixture is waiting for a result it can still get.
RESULTS_CATCH_UP_DELAY_SECONDS = 150
RESULTS_WINDOW_DAYS = 3


def needs_results_catch_up(now: datetime | None = None) -> bool:
    """True if a fixture from the API has kicked off and finished but has no result yet."""
    from app.models.match import Match

    now = now or datetime.now(UTC).replace(tzinfo=None)
    session = SessionLocal()
    try:
        waiting = (
            session.query(Match.id)
            .filter(
                Match.sport == "football",
                Match.status == "scheduled",
                Match.external_id.like("apif-%"),
                Match.match_date < now - timedelta(hours=3),
                Match.match_date >= now - timedelta(days=RESULTS_WINDOW_DAYS),
            )
            .first()
        )
        return waiting is not None
    except Exception as exc:  # a missing table or a locked database must not stop startup
        logger.warning("Could not check for fixtures waiting on a result: %s", exc)
        return False
    finally:
        session.close()


def needs_catch_up(now: datetime | None = None) -> bool:
    """True if the data is old enough, or unknown enough, to refresh at startup."""
    age = hours_since_refresh(now)
    return age is None or age > CATCH_UP_AFTER_HOURS


# What each API job may spend in one run, and when it runs, per plan.
#
# The free plan allows 100 requests a day. The numbers below are worst cases and
# add up to 99 on it:
#
#     fixtures   3 runs x 3 days                    =   9
#     odds       2 runs x (3 days x 3 pages + 10)   =  38
#     results    4 runs x 3 days                    =  12
#     stats      1 run  x 10 fixtures x 2 requests  =  20
#     injuries   1 run  x 10 teams x 2 requests     =  20
#
# A paid plan allows thousands, so it gets the original, busier cadence and
# larger caps. Which one applies is read from the account's own daily limit, not
# configured by hand, so upgrading the plan changes the behaviour with no edit.
# An unreadable status falls back to the free profile: the safe one.
PROFILES: dict[str, dict] = {
    "free": {
        "fixtures": {"days": 3, "cron": {"hour": "*/8"}},
        "odds": {"days": 3, "backfill": 10, "cron": {"hour": "*/12", "minute": 15}},
        "results": {"days": 3, "cron": {"hour": "*/6"}},
        # Live scores: one request per poll. On the free plan a poll only runs while at least
        # `reserve` requests remain, so it can never starve the jobs above of their share.
        "live": {"minutes": 30, "reserve": 40},
        "stats": {"fixtures": 10, "cron": {"hour": 5, "minute": 10}},
        "injuries": {"teams": 10},
    },
    "paid": {
        "fixtures": {"days": 7, "cron": {"hour": "*/4"}},
        "odds": {"days": 3, "backfill": 40, "cron": {"hour": "*/4", "minute": 15}},
        "results": {"days": 2, "cron": {"minute": "*/15"}},
        "live": {"minutes": 2, "reserve": 0},
        "stats": {"fixtures": 40, "cron": {"hour": "*/3", "minute": 10}},
        "injuries": {"teams": 100},
    },
}

# Requests a paid plan may spend per results run looking up fixtures the by-date fetch missed.
STALE_REQUESTS = 5

# One odds page is up to this many requests per day on the free plan's cap.
ODDS_PAGES_PER_DAY = 3

# How far ahead "playing soon" looks when choosing teams whose injuries matter.
INJURY_LOOKAHEAD_DAYS = 3


def _profile_for(limit: int) -> dict:
    return PROFILES["paid" if limit >= PAID_DAILY_LIMIT else "free"]


def _admit(name: str, settings, cost_for) -> dict | None:
    """Decide whether an API job may run now. Returns its plan profile, or None.

    `cost_for(profile)` is the job's worst-case spend. The job runs only if that
    fits in what the account has left today, read from API-Football itself, with a
    margin spare. If the status cannot be read the job is skipped: one missed run
    is cheap, and a spent quota is not.
    """
    if not settings.api_football_key:
        logger.info("%s skipped: API_FOOTBALL_KEY not set", name)
        return None
    status = api_status(settings)
    if status is None:
        logger.warning("%s skipped: could not read the API quota", name)
        return None
    profile = _profile_for(status["limit"])
    cost = cost_for(profile)
    remaining = status["limit"] - status["used"]
    if remaining < cost + MARGIN:
        logger.warning(
            "%s skipped: needs up to %d requests but only %d of today's %d remain",
            name,
            cost,
            remaining,
            status["limit"],
        )
        return None
    return profile


def refresh_data_job() -> None:
    """Daily: re-download every league from the free source, re-clean, re-load.

    Football-Data.co.uk publishes whole-season files rather than a single-day
    feed, so "daily refresh" means re-pulling the current season's file for every
    league (results and newly completed matches land in it). That is the 19 main
    leagues by season code plus the 16 country files by year. None of it touches
    the API-Football quota, which is why it is the part of the pipeline that keeps
    the domestic record current whatever plan the account is on.

    It once pulled only the Premier League's 2024-25 season, which is how the
    whole domestic record went stale by a year: the season it fetched was over
    and no other league was fetched at all. Safe and idempotent per
    `scripts/load_to_db.py`'s own guarantees; a failed download skips that file
    and carries on.

    Runs one at a time (the 03:00 run and the startup catch-up are this same job),
    and records when it completed — only when it did.
    """
    if not _refresh_lock.acquire(blocking=False):
        logger.info("refresh_data_job skipped: a refresh is already running")
        return
    try:
        _refresh_data()
    finally:
        _refresh_lock.release()


def _refresh_data() -> None:
    from scripts.clean_data import main as clean_main
    from scripts.download_data import KNOWN_LEAGUES, download_season
    from scripts.fetch_extra_league import EXTRA_LEAGUES, write_seasons
    from scripts.load_to_db import main as load_main

    today = datetime.now(UTC).date()
    fetched = failed = 0

    for code in season_codes_to_refresh(today):
        for league in KNOWN_LEAGUES:
            if download_season(league, code) is None:
                failed += 1
            else:
                fetched += 1

    # Bare starting years: a calendar-year league's current season starts this
    # year, a split-year league's started this year or last.
    years = [today.year - 1, today.year]
    for spec in EXTRA_LEAGUES:
        try:
            saved = write_seasons(spec.country, spec.league, spec.code, years)
        except Exception as exc:  # one country's outage must not stop the rest
            logger.warning("refresh_data_job: %s failed: %s", spec.country, exc)
            failed += 1
            continue
        fetched += len(saved)

    logger.info("refresh_data_job: %d file(s) refreshed, %d failed", fetched, failed)
    clean_main()
    load_main()
    # Last, so an exception anywhere above leaves the old marker and the data
    # still reads as stale.
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    LAST_REFRESH_MARKER.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")
    logger.info("refresh_data_job completed")


def _teams_playing_soon(session, limit: int):
    """Teams with a football fixture in the next few days, soonest first, capped.

    Injuries matter for a team that is about to play. The sync once looped over
    every team in the database — tennis players among them — which is thousands of
    requests for news about clubs with nothing on the calendar.
    """
    from datetime import UTC, datetime, timedelta

    from app.models import Match, Team

    now = datetime.now(UTC).replace(tzinfo=None)
    fixtures = (
        session.query(Match)
        .filter(
            Match.status == "scheduled",
            Match.sport == "football",
            Match.match_date >= now,
            Match.match_date < now + timedelta(days=INJURY_LOOKAHEAD_DAYS),
        )
        .order_by(Match.match_date.asc())
        .all()
    )
    ids: list[int] = []
    for match in fixtures:
        for team_id in (match.home_team_id, match.away_team_id):
            if team_id not in ids:
                ids.append(team_id)
    ids = ids[:limit]
    by_id = {t.id: t for t in session.query(Team).filter(Team.id.in_(ids))} if ids else {}
    return [by_id[i] for i in ids if i in by_id]


def sync_injuries_job() -> None:
    """Daily: refresh injuries for teams that are about to play — best effort.

    Skipped (not a scheduler failure) without an API key, or when the day's quota
    cannot cover it. The team count is capped per plan, and each team costs up to
    two requests (resolving its API id, then fetching injuries).
    """
    settings = get_settings()
    profile = _admit("sync_injuries_job", settings, lambda p: 2 * p["injuries"]["teams"])
    if profile is None:
        return

    from scripts.sync_injuries import ApiFootballError, sync_team_injuries

    session = SessionLocal()
    try:
        for team in _teams_playing_soon(session, profile["injuries"]["teams"]):
            try:
                sync_team_injuries(session, team, settings)
            except ApiFootballError as exc:
                logger.warning("sync_injuries_job skipping %s: %s", team.name, exc)
    finally:
        session.close()


def fetch_upcoming_fixtures_job() -> None:
    """Ingest newly-announced fixtures for every modelled competition.

    Fixture lists roll forward day by day — a free API-Football plan only ever
    shows a few days ahead at any one moment — so running this regularly is what
    turns that narrow window into a continuously up-to-date board instead of a
    one-off snapshot. One request per day looked at, so the cost is the number of
    days; the free profile looks three ahead, the window it can actually answer.
    """
    settings = get_settings()
    profile = _admit("fetch_upcoming_fixtures_job", settings, lambda p: p["fixtures"]["days"])
    if profile is None:
        return

    from scripts.fetch_upcoming_fixtures import main as fetch_fixtures_main

    fetch_fixtures_main(["--days", str(profile["fixtures"]["days"])])


def fetch_odds_job() -> None:
    """Refresh bookmaker prices for upcoming fixtures.

    Runs after the fixtures job so freshly-ingested fixtures already exist to
    attach prices to. The bulk call paginates, up to three pages a day on a free
    plan, and a per-fixture fallback fills what it missed up to a cap; both are
    counted in the worst case.
    """
    settings = get_settings()
    profile = _admit(
        "fetch_odds_job",
        settings,
        lambda p: p["odds"]["days"] * ODDS_PAGES_PER_DAY + p["odds"]["backfill"],
    )
    if profile is None:
        return

    from scripts.fetch_odds import main as fetch_odds_main

    odds = profile["odds"]
    fetch_odds_main(["--days", str(odds["days"]), "--max-backfill", str(odds["backfill"])])


def fetch_results_job() -> None:
    """Fill in results for fixtures that have finished.

    `evaluate_predictions_job` (below) can only backfill actual results onto
    `prediction_history` once a match's row says `status="completed"` — this is
    what flips it. One request per day walked back, so the cost is the number of
    days.
    """
    settings = get_settings()
    profile = _admit(
        "fetch_results_job",
        settings,
        lambda p: p["results"]["days"] + (STALE_REQUESTS if p is PROFILES["paid"] else 0),
    )
    if profile is None:
        return

    from scripts.fetch_results import fetch_and_apply_results, resolve_stale_fixtures

    updated = fetch_and_apply_results(days_back=profile["results"]["days"])
    logger.info("fetch_results_job marked %d fixture(s) completed", updated)
    if profile is PROFILES["paid"]:
        # Only a paid plan can look a fixture up by id, which is how one that slipped past the
        # by-date window (the backend was off while it was reachable) is finally settled.
        settled = resolve_stale_fixtures(
            older_than_days=profile["results"]["days"], max_requests=STALE_REQUESTS
        )
        logger.info("fetch_results_job settled %d stale fixture(s)", settled)


def fetch_live_job() -> None:
    """Football scores for matches in play, one request.

    Skipped without spending anything when no fixture could be in play (checked against the
    database first), and, on a free plan, when fewer than the profile's `reserve` requests
    remain, which leaves the day's fixtures, odds and results jobs their share.
    """
    settings = get_settings()
    session = SessionLocal()
    try:
        from app.services.live_scores import needs_live_poll, refresh_live_scores

        if not needs_live_poll(session):
            return
        profile = _admit("fetch_live_job", settings, lambda p: 1 + p["live"]["reserve"])
        if profile is None:
            return
        result = refresh_live_scores(
            session,
            settings.api_football_key,
            settings.api_football_base_url,
            # Only a paid plan may look a fixture up by id; that is what settles a match
            # within a poll of full time.
            lookup_ended=profile is PROFILES["paid"],
        )
        logger.info("fetch_live_job: %s", result)
        if result["settled"]:
            from app.services.elo_sync import sync_elo

            sync_elo(session, "football")
    except Exception:  # noqa: BLE001 - a failed poll is retried on the next tick
        logger.exception("fetch_live_job failed")
        session.rollback()
    finally:
        session.close()


def fetch_match_stats_job() -> None:
    """Per-fixture statistics and goal events for matches that now have a score.

    Two requests per fixture, so this is deliberately its own job with its own cap
    rather than folded into the results job: it is the one whose cost scales with
    how much football was played.
    """
    settings = get_settings()
    profile = _admit("fetch_match_stats_job", settings, lambda p: 2 * p["stats"]["fixtures"])
    if profile is None:
        return

    from scripts.fetch_match_stats import fetch_and_apply_match_stats

    updated = fetch_and_apply_match_stats(max_fixtures=profile["stats"]["fixtures"])
    logger.info("fetch_match_stats_job fetched statistics/events for %d fixture(s)", updated)


def evaluate_predictions_job() -> None:
    """After matches: backfill actual results onto prediction_history."""
    from ml.monitoring.evaluation import backfill_actual_results

    session = SessionLocal()
    try:
        updated = backfill_actual_results(session)
        logger.info("evaluate_predictions_job backfilled %d rows", updated)
    finally:
        session.close()


def retrain_models_job() -> None:
    """Weekly: retrain every model (including every line of every multi-line
    market) and regenerate the performance report."""
    from ml.prediction.predict import CARDS_LINES, CORNERS_LINES, GOALS_LINES, HT_GOALS_LINES
    from ml.prediction.predict_basketball import TOTAL_POINTS_LINES
    from ml.prediction.predict_tennis import TOTAL_GAMES_LINES
    from ml.training.train_basketball_totals import train as train_basketball_totals
    from ml.training.train_basketball_winner import train as train_basketball_winner
    from ml.training.train_btts import train as train_btts
    from ml.training.train_cards import train as train_cards
    from ml.training.train_corners import train as train_corners
    from ml.training.train_ht_goals import train as train_ht_goals
    from ml.training.train_match_result import train as train_match_result
    from ml.training.train_over_under import train as train_over_under
    from ml.training.train_tennis_totals import train as train_tennis_totals
    from ml.training.train_tennis_winner import train as train_tennis_winner

    jobs = [
        ("xgboost_match_result", lambda: train_match_result()),
        ("gbm_btts", lambda: train_btts()),
    ]
    jobs += [
        (f"goals {line}", lambda line=line: train_over_under(line=line)) for line in GOALS_LINES
    ]
    jobs += [
        (f"ht_goals {line}", lambda line=line: train_ht_goals(line=line)) for line in HT_GOALS_LINES
    ]
    jobs += [
        (f"corners {line}", lambda line=line: train_corners(line=line)) for line in CORNERS_LINES
    ]
    jobs += [(f"cards {line}", lambda line=line: train_cards(line=line)) for line in CARDS_LINES]
    # Basketball. These raise SystemExit when no basketball data has been
    # ingested, which the loop below already treats as "skip", so a
    # football-only deployment is unaffected.
    jobs += [("basketball_winner", lambda: train_basketball_winner())]
    jobs += [
        (f"basketball_total {line}", lambda line=line: train_basketball_totals(line=line))
        for line in TOTAL_POINTS_LINES
    ]
    # Tennis. Same "SystemExit means no data ingested, so skip" contract.
    jobs += [("tennis_winner", lambda: train_tennis_winner())]
    jobs += [
        (f"tennis_total_games {line}", lambda line=line: train_tennis_totals(line=line))
        for line in TOTAL_GAMES_LINES
    ]

    for name, train_fn in jobs:
        try:
            metrics = train_fn()
            logger.info("retrain_models_job trained %s: %s", name, metrics)
        except SystemExit as exc:
            logger.warning("retrain_models_job skipped %s: %s", name, exc)

    generate_report_job()


def generate_report_job() -> None:
    """Weekly (after retraining): regenerate the calibration/drift report."""
    from scripts.generate_report import main as report_main

    report_main()


def archive_and_cleanup_job() -> None:
    """Monthly: log a summary of model versions for manual archive/cleanup review.

    Deliberately does not auto-delete model artifacts or database rows —
    "archive models, clean datasets, backup database" (spec Step 12) each
    carry real data-loss risk, so this job reports what *could* be archived
    and leaves the destructive step to a human running it deliberately.
    """
    from app.models import ModelVersion

    session = SessionLocal()
    try:
        inactive = (
            session.query(ModelVersion)
            .filter(ModelVersion.is_active.is_(False))
            .order_by(ModelVersion.trained_at.asc())
            .all()
        )
        logger.info(
            "archive_and_cleanup_job: %d inactive model version(s) are archive candidates: %s",
            len(inactive),
            [f"{m.model_name}:{m.version}" for m in inactive],
        )
    finally:
        session.close()


def nightly_backup_job() -> None:
    """Nightly: a verified snapshot of the database, kept beside it, newest `backup_keep`.

    The database holds what cannot be rebuilt: stored pre-kick-off predictions, the live record,
    and now the members, posts and subscriptions. This uses SQLite's own backup API (see
    `scripts/backup_db.py`), so it is consistent while the engine is writing and is checked to
    open and pass `integrity_check` before an older one is deleted. It is the same disk, so it
    guards against a bad edit or a corrupt write, not a lost server: a copy still has to leave
    the machine (docs/deployment.md, "Backups").

    It refuses to run when the disk could not hold the copy twice over, rather than fill the
    disk the engine itself runs on, and says so in the log.
    """
    from scripts.backup_db import backup, sqlite_path

    settings = get_settings()
    if not settings.is_sqlite:
        logger.info("nightly_backup_job: not a SQLite database, nothing to do")
        return
    try:
        source = sqlite_path(settings.database_url)
        out_dir = source.parent / "backups"
        if shutil.disk_usage(source.parent).free < 2 * source.stat().st_size:
            logger.error(
                "nightly_backup_job: not enough free disk space for a copy of %s; skipped",
                source,
            )
            return
        target = backup(source, out_dir, keep=max(1, settings.backup_keep))
    except (SystemExit, OSError) as exc:
        # `backup` exits (rather than raises) when the copy fails its integrity check.
        logger.error("nightly_backup_job: the backup failed: %s", exc)
        return
    logger.info("nightly_backup_job: wrote %s (%.1f MB)", target, target.stat().st_size / 1_048_576)


def strip_canary_job() -> None:
    """Every few minutes: rebuild the home page's results strip and shout if it would vanish.

    The strip of graded picks under the hero has disappeared more than once, each time
    for a different reason and each time a visitor noticed first. This job is the "did
    it come back" check that runs without anyone looking. It uses no API quota. It
    rebuilds the strip's data (so a visitor's request almost always finds it fresh and
    never waits on a cold read), and it logs an ERROR if there are too few graded picks
    for the website to show the strip, or if the rebuild fails, so the problem is in the
    log before it is on the page.
    """
    from app.services.recent_results import MIN_STRIP_ITEMS, refresh

    session = SessionLocal()
    try:
        result = refresh(session)
        if result["count"] < MIN_STRIP_ITEMS:
            logger.error(
                "strip canary: only %d graded picks for the results strip (it needs %d); "
                "the home page will hide it until more matches are graded",
                result["count"],
                MIN_STRIP_ITEMS,
            )
    except Exception:  # noqa: BLE001 - a canary must report, never crash the scheduler
        logger.exception("strip canary: could not rebuild the results strip")
    finally:
        session.close()


# Basketball quota held back for the day's date-window runs when backfilling history.
BASKETBALL_FEED_RESERVE = 25


def basketball_feed_job() -> None:
    """Every few hours: today's basketball games across every league, then ratings and picks.

    One date-window request set (yesterday, today, tomorrow) brings in every league's
    fixtures and results. It spends the basketball quota (a handful of requests), so it
    asks the provider what is left first and spends nothing if that cannot be read.
    Then the ratings are brought up to date and the next day and a half of fixtures are
    priced and stored, so a pick exists before the game starts.
    """
    from app.services import basketball_feed
    from app.services.elo_sync import sync_elo
    from app.services.sport_predictions import store_upcoming

    session = SessionLocal()
    try:
        result = basketball_feed.sync_date_window(session)
        logger.info("basketball feed: %s", result)
        sync_elo(session, "basketball")
        logger.info("basketball picks: %s", store_upcoming(session, sports=("basketball",)))
    except Exception:  # noqa: BLE001 - one bad run must not stop the scheduler
        logger.exception("basketball feed failed")
        session.rollback()
    finally:
        session.close()


def basketball_backfill_job() -> None:
    """Once a day: fetch more basketball history with whatever quota the feed leaves.

    A league's ratings come from its past seasons, one request per league-season, and
    there are hundreds of them. This works through them best-known leagues first, keeping
    enough quota back for the day's date-window requests. When nothing is left to fetch
    it does nothing.
    """
    from app.services import basketball_feed
    from app.services.elo_sync import sync_elo

    session = SessionLocal()
    try:
        left = basketball_feed.requests_left(get_settings())
        if left is None:
            return
        # Keep the rest of the day's date-window runs (about 3 requests each) funded.
        spare = left - BASKETBALL_FEED_RESERVE
        if spare <= 0:
            return
        result = basketball_feed.backfill(session, max_requests=spare)
        logger.info("basketball backfill: %s", result)
        if result.get("inserted"):
            sync_elo(session, "basketball")
    except Exception:  # noqa: BLE001
        logger.exception("basketball backfill failed")
        session.rollback()
    finally:
        session.close()


def tennis_feed_job() -> None:
    """Every half hour: tennis fixtures and results, then ratings and picks.

    The scoreboard feed needs no quota. The historical workbook for the current year is
    re-read when its cached copy is a day old, and adopts any match the scoreboard
    already held. Ratings are updated for the new results and the next day and a half
    of fixtures are priced and stored.
    """
    from app.services import tennis_feed
    from app.services.elo_sync import sync_elo
    from app.services.sport_predictions import store_upcoming
    from scripts.fetch_tennis import refresh_current_year

    session = SessionLocal()
    try:
        try:
            refresh_current_year(session)
        except Exception:  # noqa: BLE001 - the workbook host being down must not block the feed
            logger.exception("tennis workbook refresh failed")
            session.rollback()
        logger.info("tennis feed: %s", tennis_feed.sync(session))
        sync_elo(session, "tennis")
        logger.info("tennis picks: %s", store_upcoming(session, sports=("tennis",)))
    except Exception:  # noqa: BLE001
        logger.exception("tennis feed failed")
        session.rollback()
    finally:
        session.close()


def engine_warm_job() -> None:
    """Every few minutes: keep the engine's expensive shared work ready.

    Loading the football history (about nine seconds) and grading every stored prediction
    (about four) are cached for several minutes. Left to the first visitor after each expiry,
    a crawler arriving then would queue behind them; this refreshes them just before they
    lapse. It also builds the day boards the home page asks for (yesterday, today, tomorrow),
    which on a cold start took a visitor 30 to 50 seconds. It uses no API quota. A failure is
    logged and the next run tries again.
    """
    from datetime import date

    from app.api.routes_board_table import MAX_FIXTURES, _board_cache, _build_board_isolated
    from app.services.prediction_service import _all_completed_history
    from app.services.progress_service import _grade_all

    session = SessionLocal()
    try:
        _all_completed_history(session, datetime.combine(date.today(), datetime.min.time()))
        _grade_all(session)
    except Exception:  # noqa: BLE001
        logger.exception("engine warm-up failed")
        session.rollback()
    finally:
        session.close()

    # The three boards the home page asks for. Built here, under the same cache key a request
    # uses, so the first visitor after a start (or after the cache lapses) is served a finished
    # board instead of waiting for the whole day's predictions to be priced. Each build uses its
    # own session (a stale entry is refreshed in the background, after this job has moved on),
    # and one slow or failing day must not stop the others.
    today = datetime.now(UTC).date()
    for offset in (0, 1, -1):
        day = today + timedelta(days=offset)
        try:
            _board_cache.get_or_compute(
                (day, None, None, "football", MAX_FIXTURES),
                lambda d=day: _build_board_isolated(d, None, None, "football", MAX_FIXTURES),
            )
        except Exception:  # noqa: BLE001
            logger.exception("board warm-up failed for %s", day)


def sports_warm_job() -> None:
    """Keep the basketball and tennis pages' data warm so no visitor pays for a cold read.

    Pricing the latest tennis matches loads the sport's whole history, which takes several
    seconds, and the answer is cached for an hour. Left to a visitor (or a crawler), the first
    request after each expiry would wait that long. So every few minutes this rebuilds, ahead of
    expiry: the page overview and summary, the boards for today and tomorrow, and each sport's
    record (which walks every graded prediction). Boards and records are held stale-while-
    revalidate (app/api/routes_sports.py), so even a request that lands between two runs is
    answered from the previous build. It uses no API quota. A failure is logged and the next run
    tries again.
    """
    from app.api.routes_sports import board_for, record_for
    from app.services.sport_service import (
        CACHE_TTL_SECONDS,
        SUMMARY_TTL_SECONDS,
        sport_overview,
        sports_summary,
    )

    # Rebuild an answer that would otherwise lapse before this job next runs (plus a margin).
    ahead = SPORTS_WARM_MINUTES * 60 + 120
    session = SessionLocal()
    try:
        try:
            sports_summary(session, max_age=SUMMARY_TTL_SECONDS - ahead)
        except Exception:  # noqa: BLE001
            logger.exception("sports warm-up: could not refresh the summary")
        for sport in ("basketball", "tennis"):
            try:
                sport_overview(session, sport, max_age=CACHE_TTL_SECONDS - ahead)
            except Exception:  # noqa: BLE001 - one sport failing must not skip the other
                logger.exception("sports warm-up: could not refresh %s", sport)
    finally:
        session.close()

    today = datetime.now(UTC).date()
    for sport in ("basketball", "tennis"):
        for offset in (0, 1):
            try:
                board_for(sport, today + timedelta(days=offset))
            except Exception:  # noqa: BLE001
                logger.exception("sports warm-up: could not build the %s board", sport)
        try:
            record_for(sport)
        except Exception:  # noqa: BLE001
            logger.exception("sports warm-up: could not build the %s record", sport)


# The job ids whose cadence follows the API plan, and how each is triggered for a profile.
def _plan_triggers(profile: dict) -> dict[str, object]:
    return {
        "fetch_upcoming_fixtures": CronTrigger(**profile["fixtures"]["cron"]),
        "fetch_odds": CronTrigger(**profile["odds"]["cron"]),
        "fetch_results": CronTrigger(**profile["results"]["cron"]),
        "fetch_match_stats": CronTrigger(**profile["stats"]["cron"]),
        "fetch_live": IntervalTrigger(minutes=profile["live"]["minutes"]),
    }


# Which profile the running jobs were scheduled with ("free" or "paid").
_active_profile_key: str | None = None


def plan_watch_job() -> None:
    """Re-read the account's plan and re-time the API jobs if it no longer matches.

    The cadence is chosen once, at start-up, from the plan the API reports. If that read failed
    (the network was not up yet right after a boot, the API was briefly down) the engine would
    have fallen back to the free-plan cadence and stayed there until the next restart, with live
    scores every half hour on a paid plan. This re-checks every half hour and fixes it in place.
    """
    global _active_profile_key
    scheduler = _scheduler
    if scheduler is None:
        return
    settings = get_settings()
    status = api_status(settings)
    if status is None:
        return  # cannot tell; keep what is running rather than guess
    wanted = "paid" if status["limit"] >= PAID_DAILY_LIMIT else "free"
    if wanted == _active_profile_key:
        return
    triggers = _plan_triggers(PROFILES[wanted])
    for job_id, trigger in triggers.items():
        try:
            scheduler.reschedule_job(job_id, trigger=trigger)
        except Exception:  # noqa: BLE001 - one missing job must not stop the rest
            logger.exception("plan_watch could not reschedule %s", job_id)
    logger.warning(
        "plan_watch: API plan is %s, jobs re-timed (was %s)", wanted, _active_profile_key
    )
    _active_profile_key = wanted


def start_scheduler() -> BackgroundScheduler | None:
    """Start the background scheduler if enabled. Idempotent — calling twice is a no-op."""
    global _scheduler
    settings = get_settings()
    if not settings.enable_scheduler:
        logger.info("Scheduler disabled (ENABLE_SCHEDULER=false)")
        return None
    if _scheduler is not None:
        return _scheduler

    # The cadence follows the account's plan, read from the API itself: a free
    # plan gets the quota-safe one, a paid plan the busier one. See PROFILES.
    global _active_profile_key
    _active_profile_key = "paid" if is_paid_plan(settings) else "free"
    profile = PROFILES[_active_profile_key]
    triggers = _plan_triggers(profile)

    scheduler = BackgroundScheduler()
    scheduler.add_job(refresh_data_job, CronTrigger(hour=3, minute=0), id="daily_refresh_data")
    scheduler.add_job(sync_injuries_job, CronTrigger(hour=3, minute=30), id="daily_sync_injuries")
    # Rolls the visible board forward as new fixtures are announced, rather than
    # only ever reflecting whatever was ingested the last time someone ran the
    # script by hand.
    scheduler.add_job(
        fetch_upcoming_fixtures_job,
        triggers["fetch_upcoming_fixtures"],
        id="fetch_upcoming_fixtures",
    )
    # After fixtures in the day, so newly-ingested rows have prices by the time
    # anyone loads the board.
    scheduler.add_job(fetch_odds_job, triggers["fetch_odds"], id="fetch_odds")
    # Runs ahead of evaluate_predictions_job's */6 cadence so a completed
    # match's result is already in the database by the time that job looks
    # for one to backfill.
    scheduler.add_job(fetch_results_job, triggers["fetch_results"], id="fetch_results")
    # Only ever sees fixtures that already have a score, so it has nothing to do
    # for one that isn't completed yet.
    scheduler.add_job(fetch_match_stats_job, triggers["fetch_match_stats"], id="fetch_match_stats")
    # Live scores for matches in play. Cadence follows the plan (see PROFILES): coarse on the
    # free plan, every couple of minutes on a paid one.
    scheduler.add_job(
        fetch_live_job,
        triggers["fetch_live"],
        id="fetch_live",
        coalesce=True,
        max_instances=1,
    )
    # Re-reads the plan so a start-up that could not read it does not strand the cadence.
    scheduler.add_job(
        plan_watch_job,
        IntervalTrigger(minutes=30),
        id="plan_watch",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(evaluate_predictions_job, CronTrigger(hour="*/6"), id="evaluate_predictions")
    # Off unless `ENABLE_WEEKLY_RETRAIN` is set. Training about thirty models inside the web
    # engine's own process held the CPU near 150% for an hour and grew the process to 3 GB on the
    # 4 GB server, until the kernel killed it (12 Oct 2026, a Monday, at 04:00). Models are
    # trained on a development machine and uploaded; see docs/deployment.md.
    if getattr(settings, "enable_weekly_retrain", False):
        scheduler.add_job(
            retrain_models_job,
            CronTrigger(day_of_week="mon", hour=4, minute=0),
            id="weekly_retrain",
        )
    scheduler.add_job(
        archive_and_cleanup_job, CronTrigger(day=1, hour=5, minute=0), id="monthly_archive"
    )
    # Quiet hour, clear of the 02:30 basketball back-fill and the 03:00 refresh.
    scheduler.add_job(
        nightly_backup_job,
        CronTrigger(hour=2, minute=10),
        id="nightly_backup",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    # The strip canary: not a data job, so it has no place in the budget profiles. It
    # also runs once straight away, so the strip's data is warm before the first visit.
    scheduler.add_job(
        strip_canary_job,
        IntervalTrigger(minutes=5),
        id="results_strip_canary",
        next_run_time=datetime.now(),
        coalesce=True,
        max_instances=1,
    )
    # Keep the football history and the graded record warm for visitors and crawlers.
    scheduler.add_job(
        engine_warm_job,
        IntervalTrigger(minutes=4),
        id="engine_warm",
        next_run_time=datetime.now() + timedelta(seconds=15),
        coalesce=True,
        max_instances=1,
    )
    # Warm the basketball and tennis pages shortly after start and then keep them warm
    # (see `sports_warm_job`). The delay keeps it out of the way of startup itself.
    scheduler.add_job(
        sports_warm_job,
        IntervalTrigger(minutes=SPORTS_WARM_MINUTES),
        id="sports_pages_warm",
        next_run_time=datetime.now() + timedelta(seconds=45),
        coalesce=True,
        max_instances=1,
    )
    # Basketball and tennis: live fixtures, results, ratings and stored picks.
    scheduler.add_job(
        basketball_feed_job,
        IntervalTrigger(hours=4),
        id="basketball_feed",
        next_run_time=datetime.now() + timedelta(seconds=90),
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        basketball_backfill_job,
        CronTrigger(hour=2, minute=30),
        id="basketball_backfill",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        tennis_feed_job,
        IntervalTrigger(minutes=30),
        id="tennis_feed",
        next_run_time=datetime.now() + timedelta(seconds=120),
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    _scheduler = scheduler

    # Catch up on a refresh the backend was not running to do. Not in the cron
    # list above: it exists only for this process, only if the data is old.
    if needs_catch_up():
        scheduler.add_job(
            refresh_data_job,
            DateTrigger(run_date=datetime.now() + timedelta(seconds=CATCH_UP_DELAY_SECONDS)),
            id="catch_up_refresh_data",
        )
        logger.info(
            "Data is older than %d hours (or has never been refreshed): refreshing in %d seconds",
            CATCH_UP_AFTER_HOURS,
            CATCH_UP_DELAY_SECONDS,
        )
    if needs_results_catch_up():
        scheduler.add_job(
            fetch_results_job,
            DateTrigger(
                run_date=datetime.now() + timedelta(seconds=RESULTS_CATCH_UP_DELAY_SECONDS)
            ),
            id="catch_up_fetch_results",
        )
        logger.info(
            "Fixtures are waiting on a result: fetching results in %d seconds",
            RESULTS_CATCH_UP_DELAY_SECONDS,
        )
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
