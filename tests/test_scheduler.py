"""Tests for app.scheduler — job wiring, not job execution (jobs call real
pipeline/training code that's already tested on its own)."""

from __future__ import annotations

import app.scheduler as scheduler_module


def test_scheduler_disabled_by_default_returns_none():
    result = scheduler_module.start_scheduler()
    assert result is None


def test_scheduler_registers_expected_jobs_when_enabled(monkeypatch):
    class FakeSettings:
        enable_scheduler = True
        api_football_key = None  # no key: the free-plan cadence, and no network

    monkeypatch.setattr(scheduler_module, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(scheduler_module, "needs_catch_up", lambda: False)
    scheduler_module._scheduler = None  # ensure a clean start regardless of test order

    try:
        started = scheduler_module.start_scheduler()
        assert started is not None
        job_ids = {job.id for job in started.get_jobs()}
        assert job_ids == {
            "daily_refresh_data",
            "daily_sync_injuries",
            "fetch_upcoming_fixtures",
            "fetch_odds",
            "fetch_results",
            "fetch_match_stats",
            "evaluate_predictions",
            "weekly_retrain",
            "monthly_archive",
            "results_strip_canary",
            "sports_pages_warm",
            "basketball_feed",
            "basketball_backfill",
            "tennis_feed",
        }

        # Calling start again while already running is a no-op, not a second scheduler.
        again = scheduler_module.start_scheduler()
        assert again is started
    finally:
        scheduler_module.stop_scheduler()
        assert scheduler_module._scheduler is None


def test_the_suite_is_isolated_from_the_scheduler_setting_in_env():
    """`.env` may turn the scheduler on for the running app; the tests must not
    follow it, or any test touching the scheduler would start real jobs."""
    from app.utils.config import get_settings

    assert get_settings().enable_scheduler is False
