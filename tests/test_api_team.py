"""Tests for GET /team/{team} — the match page's Form and Statistics tabs."""

from __future__ import annotations

from datetime import datetime

from app.models import Match, Team


def _seed(db_session):
    arsenal = Team(name="Arsenal", league="English Premier League", sport="football")
    chelsea = Team(name="Chelsea", league="English Premier League", sport="football")
    db_session.add_all([arsenal, chelsea])
    db_session.flush()

    db_session.add_all(
        [
            Match(
                match_date=datetime(2026, 1, 1),
                competition="English Premier League",
                season="2025-2026",
                home_team_id=arsenal.id,
                away_team_id=chelsea.id,
                home_score=2,
                away_score=1,
                status="completed",
                sport="football",
                home_shots=14,
                away_shots=9,
                home_corners=7,
            ),
            Match(
                match_date=datetime(2025, 1, 1),
                competition="English Premier League",
                season="2024-2025",
                home_team_id=arsenal.id,
                away_team_id=chelsea.id,
                home_score=1,
                away_score=1,
                status="completed",
                sport="football",
                home_shots=99,  # a different season — must not leak in
            ),
        ]
    )
    db_session.commit()
    return arsenal


def test_team_detail_carries_season_stats(client, db_session):
    _seed(db_session)
    response = client.get("/team/Arsenal")
    assert response.status_code == 200
    body = response.json()

    season_stats = body["season_stats"]
    assert season_stats["season"] == "2025-2026"
    assert season_stats["matches_played"] == 1
    assert season_stats["shots"]["value"] == 14.0
    assert season_stats["shots"]["sample_size"] == 1
    assert season_stats["corners"]["value"] == 7.0
    # Never fetched for this team/season — None, not a fabricated 0.0.
    assert season_stats["possession"]["value"] is None
    assert season_stats["possession"]["sample_size"] == 0


def test_a_team_with_no_history_has_no_season_stats(client, db_session):
    lone = Team(name="Brand New FC", league="Test League", sport="football")
    db_session.add(lone)
    db_session.commit()

    response = client.get("/team/Brand New FC")
    assert response.status_code == 200
    assert response.json()["season_stats"] is None
