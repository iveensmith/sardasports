"""Tests for GET /matches and GET /competitions — the dashboard's match picker."""

from __future__ import annotations

from datetime import datetime

from app.models import Match, Team


def _seed(db_session):
    arsenal = Team(name="Arsenal")
    chelsea = Team(name="Chelsea")
    everton = Team(name="Everton")
    db_session.add_all([arsenal, chelsea, everton])
    db_session.flush()

    matches = [
        Match(
            match_date=datetime(2024, 1, 1),
            competition="English Premier League",
            season="2023-2024",
            home_team_id=arsenal.id,
            away_team_id=chelsea.id,
            home_score=2,
            away_score=1,
            status="completed",
            odds_home_win=2.0,
            odds_draw=3.4,
            odds_away_win=3.8,
        ),
        Match(
            match_date=datetime(2024, 1, 8),
            competition="English Premier League",
            season="2023-2024",
            home_team_id=everton.id,
            away_team_id=chelsea.id,
            status="scheduled",
        ),
        Match(
            match_date=datetime(2023, 5, 1),
            competition="English Premier League",
            season="2022-2023",
            home_team_id=arsenal.id,
            away_team_id=everton.id,
            home_score=1,
            away_score=1,
            status="completed",
        ),
        Match(
            match_date=datetime(2024, 2, 1),
            competition="Spanish La Liga",
            season="2023-2024",
            home_team_id=chelsea.id,
            away_team_id=everton.id,
            home_score=0,
            away_score=0,
            status="completed",
        ),
    ]
    db_session.add_all(matches)
    db_session.commit()
    return arsenal, chelsea, everton


def test_list_matches_returns_all_by_default(client, db_session):
    _seed(db_session)
    response = client.get("/matches")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 4
    assert len(body["matches"]) == 4
    # Sorted most-recent first.
    assert body["matches"][0]["match_date"] > body["matches"][-1]["match_date"]


def test_list_matches_filters_by_competition(client, db_session):
    _seed(db_session)
    response = client.get("/matches", params={"competition": "Spanish La Liga"})
    body = response.json()
    assert body["count"] == 1
    assert body["matches"][0]["competition"] == "Spanish La Liga"


def test_list_matches_filters_by_season(client, db_session):
    _seed(db_session)
    response = client.get("/matches", params={"season": "2022-2023"})
    body = response.json()
    assert body["count"] == 1
    assert body["matches"][0]["season"] == "2022-2023"


def test_list_matches_filters_by_status(client, db_session):
    _seed(db_session)
    response = client.get("/matches", params={"status": "scheduled"})
    body = response.json()
    assert body["count"] == 1
    assert body["matches"][0]["status"] == "scheduled"


def test_list_matches_filters_by_team(client, db_session):
    _seed(db_session)
    response = client.get("/matches", params={"team": "Arsenal"})
    body = response.json()
    assert body["count"] == 2
    for m in body["matches"]:
        assert "Arsenal" in (m["home_team"], m["away_team"])


def test_list_matches_unknown_team_returns_empty_not_error(client, db_session):
    _seed(db_session)
    response = client.get("/matches", params={"team": "Nonexistent FC"})
    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_list_matches_reports_has_odds_correctly(client, db_session):
    _seed(db_session)
    response = client.get(
        "/matches", params={"competition": "English Premier League", "season": "2023-2024"}
    )
    by_status = {m["status"]: m for m in response.json()["matches"]}
    assert by_status["completed"]["has_odds"] is True
    assert by_status["scheduled"]["has_odds"] is False


def test_list_matches_pagination(client, db_session):
    _seed(db_session)
    response = client.get("/matches", params={"limit": 2, "offset": 0})
    body = response.json()
    assert body["count"] == 4  # total, independent of page size
    assert len(body["matches"]) == 2


def test_list_competitions_groups_seasons_correctly(client, db_session):
    _seed(db_session)
    response = client.get("/competitions")
    assert response.status_code == 200
    body = response.json()
    by_name = {c["competition"]: c for c in body["competitions"]}

    assert by_name["English Premier League"]["seasons"] == ["2022-2023", "2023-2024"]
    assert by_name["English Premier League"]["match_count"] == 3
    assert by_name["Spanish La Liga"]["seasons"] == ["2023-2024"]
    assert by_name["Spanish La Liga"]["match_count"] == 1


def test_list_competitions_empty_when_no_matches(client):
    response = client.get("/competitions")
    assert response.status_code == 200
    assert response.json()["competitions"] == []
