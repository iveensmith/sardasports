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

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database.session import SessionLocal
from app.utils.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def refresh_data_job() -> None:
    """Daily: re-download the configured league/seasons, re-clean, re-load.

    Football-Data.co.uk publishes whole-season files rather than a
    single-day feed, so "daily fixture refresh" here means re-pulling the
    current season's file (results and any newly-completed matches land in
    it) — safe and idempotent per `scripts/load_to_db.py`'s own guarantees.
    """
    from scripts.clean_data import main as clean_main
    from scripts.download_data import download_season
    from scripts.load_to_db import main as load_main

    settings = get_settings()
    for season in settings.scheduler_seasons.split(","):
        download_season(settings.scheduler_league, season.strip())
    clean_main()
    load_main()
    logger.info("refresh_data_job completed")


def sync_injuries_job() -> None:
    """Daily: refresh injuries for every team in the configured league — best
    effort, skipped entirely (not a scheduler failure) if API_FOOTBALL_KEY
    isn't set, since this is an optional feature that needs your own key."""
    settings = get_settings()
    if not settings.api_football_key:
        logger.info("sync_injuries_job skipped: API_FOOTBALL_KEY not set")
        return

    from scripts.sync_injuries import ApiFootballError, sync_team_injuries

    session = SessionLocal()
    try:
        from app.models import Team

        teams = session.query(Team).all()
        for team in teams:
            try:
                sync_team_injuries(session, team, settings)
            except ApiFootballError as exc:
                logger.warning("sync_injuries_job skipping %s: %s", team.name, exc)
    finally:
        session.close()


def fetch_upcoming_fixtures_job() -> None:
    """Daily: ingest newly-announced fixtures for every modelled competition.

    Fixture lists roll forward day by day — a free API-Football plan only
    ever shows a few days ahead at any one moment — so running this daily is
    what turns that narrow window into a continuously up-to-date board
    instead of a one-off snapshot from whenever someone last ran it by hand.
    Skipped entirely, not a scheduler failure, if `API_FOOTBALL_KEY` isn't
    set, matching `sync_injuries_job`'s convention.
    """
    settings = get_settings()
    if not settings.api_football_key:
        logger.info("fetch_upcoming_fixtures_job skipped: API_FOOTBALL_KEY not set")
        return

    from scripts.fetch_upcoming_fixtures import main as fetch_fixtures_main

    fetch_fixtures_main([])


def fetch_odds_job() -> None:
    """Daily: refresh bookmaker prices for upcoming fixtures.

    Runs after `fetch_upcoming_fixtures_job` so freshly-ingested fixtures
    already exist to attach prices to. Skipped entirely, not a scheduler
    failure, if `API_FOOTBALL_KEY` isn't set.
    """
    settings = get_settings()
    if not settings.api_football_key:
        logger.info("fetch_odds_job skipped: API_FOOTBALL_KEY not set")
        return

    from scripts.fetch_odds import main as fetch_odds_main

    fetch_odds_main([])


def fetch_results_job() -> None:
    """Every few hours: fill in results for fixtures that have finished.

    `evaluate_predictions_job` (below) can only backfill actual results onto
    `prediction_history` once a match's row says `status="completed"` — this
    is what flips it. Skipped entirely, not a scheduler failure, if
    `API_FOOTBALL_KEY` isn't set, matching `sync_injuries_job`'s convention:
    this pipeline only exists for a deployment that opted into API-Football
    fixtures in the first place.
    """
    settings = get_settings()
    if not settings.api_football_key:
        logger.info("fetch_results_job skipped: API_FOOTBALL_KEY not set")
        return

    from scripts.fetch_results import fetch_and_apply_results

    updated = fetch_and_apply_results()
    logger.info("fetch_results_job marked %d fixture(s) completed", updated)


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


def start_scheduler() -> BackgroundScheduler | None:
    """Start the background scheduler if enabled. Idempotent — calling twice is a no-op."""
    global _scheduler
    settings = get_settings()
    if not settings.enable_scheduler:
        logger.info("Scheduler disabled (ENABLE_SCHEDULER=false)")
        return None
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(refresh_data_job, CronTrigger(hour=3, minute=0), id="daily_refresh_data")
    scheduler.add_job(sync_injuries_job, CronTrigger(hour=3, minute=30), id="daily_sync_injuries")
    # Runs a few times a day so the visible board rolls forward as new
    # fixtures are announced, rather than only ever reflecting whatever was
    # ingested the last time someone ran the script by hand.
    scheduler.add_job(
        fetch_upcoming_fixtures_job, CronTrigger(hour="*/4"), id="fetch_upcoming_fixtures"
    )
    # Right after fixtures, so newly-ingested rows have prices by the time
    # anyone loads the board.
    scheduler.add_job(fetch_odds_job, CronTrigger(hour="*/4", minute=15), id="fetch_odds")
    # Runs ahead of evaluate_predictions_job's */6 cadence so a completed
    # match's result is already in the database by the time that job looks
    # for one to backfill.
    scheduler.add_job(fetch_results_job, CronTrigger(hour="*/3"), id="fetch_results")
    scheduler.add_job(evaluate_predictions_job, CronTrigger(hour="*/6"), id="evaluate_predictions")
    scheduler.add_job(
        retrain_models_job, CronTrigger(day_of_week="mon", hour=4, minute=0), id="weekly_retrain"
    )
    scheduler.add_job(
        archive_and_cleanup_job, CronTrigger(day=1, hour=5, minute=0), id="monthly_archive"
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
