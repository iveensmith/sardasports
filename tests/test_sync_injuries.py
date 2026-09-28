"""Tests for scripts.sync_injuries — mocked HTTP, no real API-Football key needed.

Mocking is appropriate here (unlike the rest of this codebase, which
deliberately avoids mocks in favor of real computation): API-Football
requires a paid/free-tier account key we don't have in CI, and the point of
these tests is to verify *our* parsing/caching/replace logic against the
documented response shape, not to test API-Football's service itself.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models import Injury, Team
from scripts.sync_injuries import (
    ApiFootballError,
    _keep_latest_entry_per_player,
    _parse_injury_entry,
    current_api_football_season,
    resolve_api_football_team_id,
    sync_team_injuries,
)


class FakeSettings:
    api_football_key = "test-key"
    api_football_base_url = "https://v3.football.api-sports.io"
    api_football_season = 2025  # fixed in tests so mocked payloads are deterministic


class FakeResponse:
    def __init__(self, json_data: dict, status_ok: bool = True):
        self._json = json_data
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise RuntimeError("HTTP error")

    def json(self):
        return self._json


def test_resolve_api_football_team_id_uses_cache_without_network_call(db_session, monkeypatch):
    team = Team(name="Arsenal", api_football_id=42)
    db_session.add(team)
    db_session.flush()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not hit the network when already cached")

    monkeypatch.setattr("scripts.sync_injuries.requests.get", fail_if_called)

    result = resolve_api_football_team_id(db_session, team, FakeSettings())
    assert result == 42


def test_resolve_api_football_team_id_resolves_and_caches(db_session, monkeypatch):
    team = Team(name="Arsenal")
    db_session.add(team)
    db_session.flush()

    monkeypatch.setattr(
        "scripts.sync_injuries.requests.get",
        lambda *a, **k: FakeResponse({"response": [{"team": {"id": 42, "name": "Arsenal"}}]}),
    )

    result = resolve_api_football_team_id(db_session, team, FakeSettings())
    assert result == 42
    assert team.api_football_id == 42


def test_resolve_api_football_team_id_no_match_returns_none(db_session, monkeypatch):
    team = Team(name="Definitely Not A Real Club")
    db_session.add(team)
    db_session.flush()

    monkeypatch.setattr(
        "scripts.sync_injuries.requests.get", lambda *a, **k: FakeResponse({"response": []})
    )

    result = resolve_api_football_team_id(db_session, team, FakeSettings())
    assert result is None
    assert team.api_football_id is None


def test_resolve_api_football_team_id_requires_key(db_session):
    team = Team(name="Arsenal")
    db_session.add(team)
    db_session.flush()

    class NoKeySettings(FakeSettings):
        api_football_key = None

    with pytest.raises(ApiFootballError):
        resolve_api_football_team_id(db_session, team, NoKeySettings())


def test_parse_injury_entry_valid_shape():
    entry = {
        "player": {
            "id": 1,
            "name": "Bukayo Saka",
            "type": "Missing Fixture",
            "reason": "Hamstring Injury",
        },
        "team": {"id": 42, "name": "Arsenal"},
        "fixture": {"id": 999, "date": "2025-03-01T15:00:00+00:00"},
        "league": {"id": 39, "season": 2025},
    }
    parsed = _parse_injury_entry(entry)
    assert parsed["player_name"] == "Bukayo Saka"
    assert parsed["injury_type"] == "Missing Fixture"
    assert parsed["reason"] == "Hamstring Injury"
    assert parsed["fixture_external_id"] == 999
    assert parsed["fixture_date"] == datetime(2025, 3, 1, 15, 0, 0)


def test_parse_injury_entry_null_player_name_returns_none_not_raise():
    # Regression test: observed live against the real API-Football response —
    # some entries have a present-but-null player.name, which `.get("name")`
    # alone doesn't catch (it's not a missing key, just a null value).
    entry = {
        "player": {"id": 1, "name": None, "type": "Questionable", "reason": "Unknown"},
        "team": {"id": 42},
        "fixture": {"id": 999, "date": "2025-03-01T15:00:00+00:00"},
    }
    assert _parse_injury_entry(entry) is None


def test_parse_injury_entry_malformed_returns_none_not_raise():
    assert _parse_injury_entry({"unexpected": "shape"}) is None


def test_sync_team_injuries_replaces_existing_rows(db_session, monkeypatch):
    team = Team(name="Arsenal", api_football_id=42)  # pre-cached, skips /teams call
    db_session.add(team)
    db_session.flush()
    db_session.add(Injury(team_id=team.id, player_name="Stale Player", source="api-football"))
    db_session.commit()

    fake_injuries_response = FakeResponse(
        {
            "errors": [],
            "response": [
                {
                    "player": {"id": 1, "name": "New Player A", "type": "Injury", "reason": "Knee"},
                    "team": {"id": 42},
                    "fixture": {"id": 1, "date": "2025-03-01T15:00:00+00:00"},
                },
                {
                    "player": {
                        "id": 2,
                        "name": "New Player B",
                        "type": "Suspension",
                        "reason": "Red card",
                    },
                    "team": {"id": 42},
                    "fixture": {"id": 2, "date": "2025-03-08T15:00:00+00:00"},
                },
            ],
        }
    )
    monkeypatch.setattr(
        "scripts.sync_injuries.requests.get", lambda *a, **k: fake_injuries_response
    )

    count = sync_team_injuries(db_session, team, FakeSettings())

    assert count == 2
    names = {
        i.player_name for i in db_session.query(Injury).filter(Injury.team_id == team.id).all()
    }
    assert names == {"New Player A", "New Player B"}
    assert team.injuries_synced_at is not None


def test_sync_team_injuries_raises_on_api_error_field(db_session, monkeypatch):
    team = Team(name="Arsenal", api_football_id=42)
    db_session.add(team)
    db_session.flush()

    monkeypatch.setattr(
        "scripts.sync_injuries.requests.get",
        lambda *a, **k: FakeResponse({"errors": {"season": "requested season not available"}}),
    )

    with pytest.raises(ApiFootballError):
        sync_team_injuries(db_session, team, FakeSettings())


def test_current_api_football_season_before_july_is_previous_year():
    # Season "2025" (2025-26) is still current in, say, March 2026.
    assert current_api_football_season(datetime(2026, 3, 1)) == 2025


def test_current_api_football_season_from_july_is_current_year():
    # By August 2026 the 2026-27 season has started.
    assert current_api_football_season(datetime(2026, 8, 1)) == 2026


def test_keep_latest_entry_per_player_collapses_season_long_log():
    # Regression test: a real API-Football response returns one row per
    # missed *fixture*, not one row per player — a season-long injury can
    # produce a dozen-plus rows for the same player. Only the most recent
    # should survive.
    entries = [
        {"player_name": "B. White", "fixture_date": datetime(2025, 8, 31), "reason": "Knee"},
        {"player_name": "B. White", "fixture_date": datetime(2026, 5, 30), "reason": "Knee"},
        {"player_name": "B. White", "fixture_date": datetime(2025, 12, 1), "reason": "Knee"},
        {"player_name": "W. Saliba", "fixture_date": datetime(2026, 1, 28), "reason": "Ankle"},
    ]
    result = _keep_latest_entry_per_player(entries)
    by_player = {e["player_name"]: e for e in result}

    assert len(result) == 2
    assert by_player["B. White"]["fixture_date"] == datetime(2026, 5, 30)
    assert by_player["W. Saliba"]["fixture_date"] == datetime(2026, 1, 28)


def test_keep_latest_entry_per_player_handles_missing_dates():
    entries = [
        {"player_name": "Player A", "fixture_date": None, "reason": "Illness"},
        {"player_name": "Player A", "fixture_date": datetime(2026, 1, 1), "reason": "Illness"},
    ]
    result = _keep_latest_entry_per_player(entries)
    assert len(result) == 1
    assert result[0]["fixture_date"] == datetime(2026, 1, 1)


def test_sync_team_injuries_deduplicates_to_one_row_per_player(db_session, monkeypatch):
    team = Team(name="Arsenal", api_football_id=42)
    db_session.add(team)
    db_session.flush()

    def make_entry(player_id, name, date):
        return {
            "player": {"id": player_id, "name": name, "type": "Missing Fixture", "reason": "Knee"},
            "team": {"id": 42},
            "fixture": {"id": player_id * 10, "date": date},
        }

    fake_response = FakeResponse(
        {
            "errors": [],
            "response": [
                make_entry(1, "B. White", "2025-08-31T15:30:00+00:00"),
                make_entry(1, "B. White", "2026-05-30T16:00:00+00:00"),
                make_entry(2, "W. Saliba", "2026-01-28T20:00:00+00:00"),
            ],
        }
    )
    monkeypatch.setattr("scripts.sync_injuries.requests.get", lambda *a, **k: fake_response)

    count = sync_team_injuries(db_session, team, FakeSettings())

    assert count == 2  # deduped from 3 fixture-level entries to 2 players
    rows = db_session.query(Injury).filter(Injury.team_id == team.id).all()
    white = next(r for r in rows if r.player_name == "B. White")
    assert white.fixture_date == datetime(2026, 5, 30, 16, 0, 0)  # kept the latest
