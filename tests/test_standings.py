"""Tests for app.services.standings_service — computed live from our own match data."""

from __future__ import annotations

from datetime import datetime

from app.models import Match, Team
from app.services.standings_service import compute_standings


def _seed_mini_league(db_session):
    a = Team(name="A")
    b = Team(name="B")
    c = Team(name="C")
    db_session.add_all([a, b, c])
    db_session.flush()

    matches = [
        # A beats B 2-0 (A: +3pts, +2gd; B: 0pts, -2gd)
        Match(
            match_date=datetime(2024, 1, 1),
            competition="Test League",
            season="2023-2024",
            home_team_id=a.id,
            away_team_id=b.id,
            home_score=2,
            away_score=0,
            status="completed",
        ),
        # B draws C 1-1
        Match(
            match_date=datetime(2024, 1, 8),
            competition="Test League",
            season="2023-2024",
            home_team_id=b.id,
            away_team_id=c.id,
            home_score=1,
            away_score=1,
            status="completed",
        ),
        # C beats A 3-1
        Match(
            match_date=datetime(2024, 1, 15),
            competition="Test League",
            season="2023-2024",
            home_team_id=c.id,
            away_team_id=a.id,
            home_score=3,
            away_score=1,
            status="completed",
        ),
        # A scheduled match should be ignored entirely
        Match(
            match_date=datetime(2024, 2, 1),
            competition="Test League",
            season="2023-2024",
            home_team_id=a.id,
            away_team_id=c.id,
            status="scheduled",
        ),
    ]
    db_session.add_all(matches)
    db_session.commit()
    return a, b, c


def test_compute_standings_totals_and_ordering(db_session):
    _seed_mini_league(db_session)
    season, table = compute_standings(db_session, "Test League")

    assert season == "2023-2024"
    assert len(table) == 3

    by_team = {row.team: row for row in table}
    # A: won vs B (3pts, +2gd), lost vs C (0pts, -2gd) -> 3pts, 0gd, played 2
    assert by_team["A"].points == 3
    assert by_team["A"].played == 2
    assert by_team["A"].goal_difference == 0
    # B: lost vs A (0pts), drew vs C (1pt) -> 1pt
    assert by_team["B"].points == 1
    # C: drew vs B (1pt), won vs A (3pts) -> 4pts
    assert by_team["C"].points == 4

    # Sorted by points descending: C (4) > A (3) > B (1).
    assert [row.team for row in table] == ["C", "A", "B"]


def test_compute_standings_ignores_scheduled_matches(db_session):
    _seed_mini_league(db_session)
    _, table = compute_standings(db_session, "Test League")
    total_played = sum(row.played for row in table)
    assert total_played == 6  # 3 completed matches * 2 teams each, not 4 matches


def test_compute_standings_unknown_competition_returns_empty(db_session):
    season, table = compute_standings(db_session, "Nonexistent League")
    assert season is None
    assert table == []


def test_compute_standings_specific_season_not_found(db_session):
    _seed_mini_league(db_session)
    season, table = compute_standings(db_session, "Test League", season="1999-2000")
    assert season == "1999-2000"
    assert table == []
