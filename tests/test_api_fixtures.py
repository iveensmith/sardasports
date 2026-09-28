"""Tests for GET /fixtures/today and GET /team, /elo error handling."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models import Match, Team


def _seed_two_teams_and_a_fixture(db_session, match_date: datetime, status: str = "scheduled"):
    home = Team(name="Arsenal", league="English Premier League", elo_rating=1600)
    away = Team(name="Chelsea", league="English Premier League", elo_rating=1550)
    db_session.add_all([home, away])
    db_session.flush()

    match = Match(
        match_date=match_date,
        competition="English Premier League",
        season="2024-2025",
        home_team_id=home.id,
        away_team_id=away.id,
        status=status,
        home_score=2 if status == "completed" else None,
        away_score=1 if status == "completed" else None,
    )
    db_session.add(match)
    db_session.commit()
    return home, away, match


def test_fixtures_today_returns_matches_on_that_date(client, db_session):
    target = datetime.now(UTC).replace(hour=15, minute=0, second=0, microsecond=0, tzinfo=None)
    _seed_two_teams_and_a_fixture(db_session, target)

    response = client.get("/fixtures/today")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["fixtures"][0]["home_team"] == "Arsenal"
    assert body["fixtures"][0]["away_team"] == "Chelsea"


def test_fixtures_today_empty_for_unused_date(client, db_session):
    response = client.get("/fixtures/today", params={"on_date": "2099-01-01"})
    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_team_not_found_returns_404(client):
    response = client.get("/team/DefinitelyNotARealTeam")
    assert response.status_code == 404


def test_elo_not_found_returns_404(client):
    response = client.get("/elo/DefinitelyNotARealTeam")
    assert response.status_code == 404


def test_history_not_found_returns_404(client):
    response = client.get("/history/999999")
    assert response.status_code == 404
