"""Tests for GET /value/{match_id}, GET /model/monitoring, and POST /analyst/{match_id}."""

from __future__ import annotations

from datetime import datetime

from app.models import Match, Team


def _seed_match_with_odds(db_session, with_odds: bool = True):
    home = Team(name="Arsenal")
    away = Team(name="Chelsea")
    db_session.add_all([home, away])
    db_session.flush()

    completed = Match(
        match_date=datetime(2024, 1, 1),
        competition="English Premier League",
        season="2023-2024",
        home_team_id=home.id,
        away_team_id=away.id,
        home_score=2,
        away_score=1,
        status="completed",
    )
    db_session.add(completed)

    fixture = Match(
        match_date=datetime(2024, 2, 1),
        competition="English Premier League",
        season="2023-2024",
        home_team_id=home.id,
        away_team_id=away.id,
        status="scheduled",
        odds_home_win=2.0 if with_odds else None,
        odds_draw=3.4 if with_odds else None,
        odds_away_win=3.8 if with_odds else None,
    )
    db_session.add(fixture)
    db_session.commit()
    return fixture


def test_value_endpoint_returns_edges_when_odds_present(client, db_session):
    fixture = _seed_match_with_odds(db_session, with_odds=True)
    response = client.get(f"/value/{fixture.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["home_team"] == "Arsenal"
    assert len(body["edges"]) == 3
    assert {"home_win", "draw", "away_win"} == {e["outcome"] for e in body["edges"]}


def test_value_endpoint_404_when_no_odds(client, db_session):
    fixture = _seed_match_with_odds(db_session, with_odds=False)
    response = client.get(f"/value/{fixture.id}")
    assert response.status_code == 404


def test_value_endpoint_404_when_match_unknown(client):
    response = client.get("/value/999999")
    assert response.status_code == 404


def test_model_monitoring_endpoint_returns_calibration_and_drift(client, db_session):
    response = client.get("/model/monitoring")
    assert response.status_code == 200
    body = response.json()
    assert "calibration" in body
    assert "drift" in body
    assert body["drift"]["model_name"] == "xgboost_match_result"


def test_analyst_endpoint_returns_503_without_api_key(client, db_session):
    # ANTHROPIC_API_KEY is intentionally unset in the test environment.
    fixture = _seed_match_with_odds(db_session, with_odds=False)
    response = client.post(f"/analyst/{fixture.id}")
    assert response.status_code == 503


def test_analyst_endpoint_404_for_unknown_match(client):
    response = client.post("/analyst/999999")
    assert response.status_code == 404
