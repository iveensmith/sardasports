"""Serving a just-expired answer at once while one background computation replaces it."""

from __future__ import annotations

import threading
import time

import pytest

from app.utils.coalesce import CoalescingCache


def _wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_a_fresh_entry_is_returned_without_recomputing():
    cache = CoalescingCache(60, stale_seconds=60)
    calls = []

    for _ in range(3):
        cache.get_or_compute("k", lambda: calls.append(1) or "v")

    assert calls == [1]


def test_an_expired_entry_is_served_at_once_and_replaced_in_the_background():
    cache = CoalescingCache(0.05, stale_seconds=60)
    cache.get_or_compute("k", lambda: "old")
    time.sleep(0.1)  # expired, but inside the stale window
    release = threading.Event()

    def slow_new():
        release.wait(3)
        return "new"

    started = time.monotonic()
    served = cache.get_or_compute("k", slow_new)

    assert served == "old"  # not "new": the caller did not wait for the rebuild
    assert time.monotonic() - started < 1.0

    release.set()
    assert _wait_for(lambda: cache.get_or_compute("k", lambda: "x") == "new")


def test_only_one_background_refresh_runs_for_many_stale_requests():
    cache = CoalescingCache(0.05, stale_seconds=60)
    cache.get_or_compute("k", lambda: "old")
    time.sleep(0.1)
    runs = []
    release = threading.Event()

    def refresh():
        runs.append(1)
        release.wait(3)
        return "new"

    for _ in range(5):
        assert cache.get_or_compute("k", refresh) == "old"
    release.set()

    assert _wait_for(lambda: cache.get_or_compute("k", lambda: "x") == "new")
    assert runs == [1]


def test_a_failed_background_refresh_keeps_serving_the_stale_answer():
    cache = CoalescingCache(0.05, stale_seconds=60)
    cache.get_or_compute("k", lambda: "old")
    time.sleep(0.1)
    attempted = threading.Event()

    def broken():
        attempted.set()
        raise RuntimeError("database is locked")

    assert cache.get_or_compute("k", broken) == "old"
    assert attempted.wait(2)
    time.sleep(0.05)

    assert cache.get_or_compute("k", lambda: "recovered") == "old"  # stale still, and another try


def test_beyond_the_stale_window_a_caller_waits_for_a_fresh_answer():
    cache = CoalescingCache(0.05, stale_seconds=0.05)
    cache.get_or_compute("k", lambda: "old")
    time.sleep(0.3)  # past ttl and past the stale window

    assert cache.get_or_compute("k", lambda: "new") == "new"


def test_without_a_stale_window_behaviour_is_unchanged():
    cache = CoalescingCache(0.05)
    cache.get_or_compute("k", lambda: "old")
    time.sleep(0.1)

    assert cache.get_or_compute("k", lambda: "new") == "new"


@pytest.mark.parametrize("copies", [True, False])
def test_a_stale_result_is_still_a_copy_when_copies_are_on(copies):
    cache = CoalescingCache(0.05, stale_seconds=60, copy_results=copies)
    original = {"rows": [1]}
    cache.get_or_compute("k", lambda: original)
    time.sleep(0.1)

    served = cache.get_or_compute("k", lambda: {"rows": [2]})

    assert (served is original) is (not copies)
