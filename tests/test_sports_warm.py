"""Basketball and tennis pages are answered from a warm cache, rebuilt ahead of visitors."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app import scheduler
from app.api import routes_sports
from app.services import sport_service


def _counting(monkeypatch, name, result):
    calls = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return result

    monkeypatch.setattr(routes_sports, name, fake)
    return calls


def test_a_board_is_built_once_however_often_it_is_asked_for(client, monkeypatch):
    calls = _counting(monkeypatch, "build_board", {"sport": "basketball", "groups": []})

    for _ in range(3):
        assert client.get("/sports/basketball/board?on_date=2026-10-15").status_code == 200

    assert len(calls) == 1


def test_different_days_and_stored_only_are_kept_apart(client, monkeypatch):
    calls = _counting(monkeypatch, "build_board", {"sport": "tennis"})

    client.get("/sports/tennis/board?on_date=2026-10-15")
    client.get("/sports/tennis/board?on_date=2026-10-16")
    client.get("/sports/tennis/board?on_date=2026-10-15&stored_only=true")

    assert len(calls) == 3


def test_a_record_is_built_once_per_sport(client, monkeypatch):
    calls = _counting(monkeypatch, "sport_record", {"sport": "x"})

    for _ in range(3):
        client.get("/sports/basketball/record")
    client.get("/sports/tennis/record")

    assert len(calls) == 2


def test_an_unknown_sport_is_still_a_404_and_builds_nothing(client, monkeypatch):
    calls = _counting(monkeypatch, "build_board", {})

    assert client.get("/sports/curling/board").status_code == 404
    assert client.get("/sports/curling/record").status_code == 404
    assert calls == []


def test_the_warm_up_builds_ahead_of_expiry_and_one_failure_does_not_stop_it(monkeypatch):
    boards, records, overviews, summaries = [], [], [], []

    def board(sport, target, **kwargs):
        boards.append((sport, target))
        if sport == "basketball" and len(boards) == 1:
            raise RuntimeError("one board fails")

    monkeypatch.setattr(routes_sports, "board_for", board)
    monkeypatch.setattr(routes_sports, "record_for", lambda sport: records.append(sport))
    monkeypatch.setattr(
        sport_service,
        "sport_overview",
        lambda db, sport, max_age=None: overviews.append((sport, max_age)),
    )
    monkeypatch.setattr(
        sport_service,
        "sports_summary",
        lambda db, max_age=None: summaries.append(max_age),
    )

    scheduler.sports_warm_job()

    today = datetime.now(UTC).date()
    assert {s for s, _ in boards} == {"basketball", "tennis"}
    assert {d for _, d in boards} == {today, date.fromordinal(today.toordinal() + 1)}
    assert sorted(records) == ["basketball", "tennis"]
    # Asked to rebuild anything that would lapse before the next run, not only what has.
    assert all(age is not None and age < sport_service.CACHE_TTL_SECONDS for _, age in overviews)
    assert summaries and summaries[0] < sport_service.SUMMARY_TTL_SECONDS


def test_an_overview_is_rebuilt_early_when_the_caller_asks_for_a_younger_one(
    db_session, monkeypatch
):
    sport_service.clear_cache()
    built = []
    monkeypatch.setattr(
        sport_service, "_compute", lambda db, sport: built.append(sport) or {"sport": sport}
    )
    ticks = iter([1000.0, 1000.0, 1000.0 + 600.0, 1000.0 + 600.0])
    monkeypatch.setattr(sport_service, "monotonic", lambda: next(ticks))

    sport_service.sport_overview(db_session, "tennis")  # built, stamped at t=1000
    sport_service.sport_overview(db_session, "tennis")  # normal lifetime: still fresh
    sport_service.sport_overview(db_session, "tennis", max_age=300)  # older than 300: rebuilt

    assert built == ["tennis", "tennis"]
    sport_service.clear_cache()
