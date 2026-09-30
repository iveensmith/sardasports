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

    monkeypatch.setattr(scheduler_module, "get_settings", lambda: FakeSettings())
    scheduler_module._scheduler = None  # ensure a clean start regardless of test order

    try:
        started = scheduler_module.start_scheduler()
        assert started is not None
        job_ids = {job.id for job in started.get_jobs()}
        assert job_ids == {
            "daily_refresh_data",
            "daily_sync_injuries",
            "fetch_results",
            "evaluate_predictions",
            "weekly_retrain",
            "monthly_archive",
        }

        # Calling start again while already running is a no-op, not a second scheduler.
        again = scheduler_module.start_scheduler()
        assert again is started
    finally:
        scheduler_module.stop_scheduler()
        assert scheduler_module._scheduler is None
