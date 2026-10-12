"""Carrying club ids between databases fills gaps and never rewrites a mapping."""

from __future__ import annotations

from app.models import Team
from scripts.team_api_ids import apply_rows, export_rows, read_csv, write_csv


def _team(db_session, name, api_id=None, sport="football"):
    team = Team(name=name, sport=sport, league="L", api_football_id=api_id)
    db_session.add(team)
    db_session.flush()
    return team


def test_a_missing_id_is_filled_and_an_existing_one_is_never_changed(db_session):
    gap = _team(db_session, "Paris SG")
    _team(db_session, "Arsenal", 42)
    other = _team(db_session, "Chelsea", 49)

    counts = apply_rows(
        db_session,
        [
            {"name": "Paris SG", "api_football_id": 85},
            {"name": "Arsenal", "api_football_id": 42},
            {"name": "Chelsea", "api_football_id": 9999},
            {"name": "Nobody FC", "api_football_id": 1},
        ],
    )

    assert counts == {"filled": 1, "already": 1, "conflict": 1, "unknown": 1}
    assert gap.api_football_id == 85
    assert other.api_football_id == 49  # the conflicting id was not applied


def test_only_football_clubs_are_touched(db_session):
    basketball = _team(db_session, "Boston Celtics", sport="basketball")

    counts = apply_rows(db_session, [{"name": "Boston Celtics", "api_football_id": 7}])

    assert counts["unknown"] == 1 and basketball.api_football_id is None


def test_export_then_read_round_trips_and_skips_clubs_without_an_id(db_session, tmp_path):
    _team(db_session, "Zulte Waregem", 631)
    _team(db_session, "Ajax", 194)
    _team(db_session, "No Id FC")

    rows = export_rows(db_session)
    path = tmp_path / "ids.csv"
    write_csv(rows, path)

    assert [r["name"] for r in rows] == ["Ajax", "Zulte Waregem"]
    assert read_csv(path) == rows
