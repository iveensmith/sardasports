"""The scheduler lives inside the backend, so a nightly run is missed whenever the
backend is not up at 03:00 — and a missed cron run is not made up. The catch-up
refreshes shortly after startup when the data is old.

What these pin down: that it triggers on the right ages, that "last refreshed"
means a refresh that *completed*, and that the catch-up and the nightly run can
never overlap.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import app.scheduler as scheduler


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduler, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(scheduler, "LAST_REFRESH_MARKER", tmp_path / "last_refresh.txt")
    return tmp_path


def _age(path, hours: float) -> None:
    """Make a file look `hours` old."""
    path.write_text("x", encoding="utf-8")
    then = (datetime.now() - timedelta(hours=hours)).timestamp()
    os.utime(path, (then, then))


# --- how old is the data -------------------------------------------------------------


def test_nothing_on_disk_means_the_age_is_unknown_and_the_data_needs_refreshing(data_dir):
    assert scheduler.hours_since_refresh() is None
    assert scheduler.needs_catch_up() is True


def test_the_marker_is_what_says_when_the_last_refresh_finished(data_dir):
    _age(data_dir / "last_refresh.txt", hours=5)
    assert 4.9 < scheduler.hours_since_refresh() < 5.1


def test_without_a_marker_the_processed_file_stands_in(data_dir):
    """A database refreshed by hand before the marker existed is not refreshed
    again for nothing."""
    _age(data_dir / "matches.csv", hours=3)
    assert 2.9 < scheduler.hours_since_refresh() < 3.1
    assert scheduler.needs_catch_up() is False


def test_the_marker_wins_over_the_processed_file(data_dir):
    _age(data_dir / "matches.csv", hours=2)  # cleaned recently...
    _age(data_dir / "last_refresh.txt", hours=40)  # ...but never completed since
    assert scheduler.hours_since_refresh() > 39
    assert scheduler.needs_catch_up() is True


@pytest.mark.parametrize(
    "hours,expected",
    [(1, False), (19.5, False), (20.5, True), (48, True)],
)
def test_it_triggers_only_once_the_data_is_older_than_the_threshold(data_dir, hours, expected):
    _age(data_dir / "last_refresh.txt", hours=hours)
    assert scheduler.needs_catch_up() is expected


# --- the refresh records when it finished — only if it did ---------------------------


@pytest.fixture
def pipeline(monkeypatch, data_dir):
    import scripts.clean_data as clean
    import scripts.download_data as download
    import scripts.fetch_extra_league as extra
    import scripts.load_to_db as load

    calls = []
    monkeypatch.setattr(download, "download_season", lambda *a, **k: "path")
    monkeypatch.setattr(extra, "write_seasons", lambda *a, **k: ["file"])
    monkeypatch.setattr(clean, "main", lambda: calls.append("clean"))
    monkeypatch.setattr(load, "main", lambda: calls.append("load"))
    return calls


def test_a_completed_refresh_writes_the_marker(pipeline, data_dir):
    assert not (data_dir / "last_refresh.txt").exists()
    scheduler.refresh_data_job()
    assert pipeline == ["clean", "load"]
    assert (data_dir / "last_refresh.txt").exists()
    assert scheduler.needs_catch_up() is False


def test_a_refresh_that_fails_partway_leaves_the_data_reading_as_stale(
    monkeypatch, pipeline, data_dir
):
    import scripts.load_to_db as load

    _age(data_dir / "last_refresh.txt", hours=30)

    def broken():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(load, "main", broken)
    with pytest.raises(RuntimeError):
        scheduler.refresh_data_job()

    # Cleaned, then died while loading: the marker must not claim it finished.
    assert scheduler.hours_since_refresh() > 29
    assert scheduler.needs_catch_up() is True
    # And the lock is released, so the next attempt is not blocked forever.
    assert scheduler._refresh_lock.acquire(blocking=False)
    scheduler._refresh_lock.release()


def test_two_refreshes_never_run_at_once(pipeline, data_dir):
    """The catch-up and the 03:00 run are the same job: each rewrites the processed
    file and rebuilds Elo, so they must not overlap."""
    assert scheduler._refresh_lock.acquire(blocking=False)  # one is already running
    try:
        scheduler.refresh_data_job()
    finally:
        scheduler._refresh_lock.release()

    assert pipeline == []  # skipped entirely, not queued behind it
    assert not (data_dir / "last_refresh.txt").exists()


def test_a_second_thread_is_turned_away_while_the_first_works(monkeypatch, pipeline, data_dir):
    import scripts.clean_data as clean

    started, release = threading.Event(), threading.Event()

    def slow_clean():
        started.set()
        release.wait(timeout=5)
        pipeline.append("clean")

    monkeypatch.setattr(clean, "main", slow_clean)
    first = threading.Thread(target=scheduler.refresh_data_job)
    first.start()
    assert started.wait(timeout=5)

    scheduler.refresh_data_job()  # arrives while the first is mid-flight
    release.set()
    first.join(timeout=5)

    assert pipeline.count("clean") == 1  # ran once, not twice


# --- startup ---------------------------------------------------------------------------


@pytest.fixture
def started(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(enable_scheduler=True, api_football_key=None),
    )
    scheduler._scheduler = None
    yield
    scheduler.stop_scheduler()


def test_stale_data_schedules_a_one_off_refresh_shortly_after_startup(monkeypatch, started):
    monkeypatch.setattr(scheduler, "needs_catch_up", lambda: True)

    running = scheduler.start_scheduler()
    job = running.get_job("catch_up_refresh_data")

    assert job is not None
    assert job.func is scheduler.refresh_data_job
    delay = (job.next_run_time.replace(tzinfo=None) - datetime.now()).total_seconds()
    # Soon, but not during startup itself: the app should be serving first.
    assert 30 < delay <= scheduler.CATCH_UP_DELAY_SECONDS + 5


def test_fresh_data_schedules_nothing_extra(monkeypatch, started):
    monkeypatch.setattr(scheduler, "needs_catch_up", lambda: False)

    running = scheduler.start_scheduler()

    assert running.get_job("catch_up_refresh_data") is None
    assert len(running.get_jobs()) == 14


def test_the_catch_up_is_in_addition_to_the_nightly_run_not_instead_of_it(monkeypatch, started):
    monkeypatch.setattr(scheduler, "needs_catch_up", lambda: True)

    running = scheduler.start_scheduler()

    assert running.get_job("daily_refresh_data") is not None
    assert running.get_job("catch_up_refresh_data") is not None
    assert len(running.get_jobs()) == 15
