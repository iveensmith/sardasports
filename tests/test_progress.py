"""Tests for the track record and its two CSV downloads.

The downloads exist so a reader can recount the page, so the property worth
pinning is that they *reconcile* with it: the same graded rows, counted three
ways, agreeing on every total.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from app.models import Match, Prediction, Team
from app.services.progress_service import build_progress


def _prediction(match_id: int, created_at: datetime) -> Prediction:
    return Prediction(
        match_id=match_id,
        created_at=created_at,
        prob_home=62.0,
        prob_draw=22.0,
        prob_away=16.0,
        expected_goals_home=2.1,
        expected_goals_away=0.9,
        top_scorelines=["2-0", "2-1"],
        prob_btts_yes=44.0,
        prob_btts_no=56.0,
        goals_markets=[
            {"line": 1.5, "prob_over": 81.0, "prob_under": 19.0, "model_used": True},
            {"line": 2.5, "prob_over": 55.0, "prob_under": 45.0, "model_used": True},
        ],
        ht_goals_markets=[],
        corners_markets=[],
        cards_markets=[],
        confidence=90.0,
    )


def _play(db_session, home: Team, away: Team, when: datetime, score: tuple[int, int]) -> Match:
    match = Match(
        match_date=when,
        competition="English Premier League",
        season="2025-2026",
        home_team_id=home.id,
        away_team_id=away.id,
        status="completed",
        home_score=score[0],
        away_score=score[1],
    )
    db_session.add(match)
    db_session.flush()
    return match


def _seed(db_session):
    """Two played fixtures: one predicted before kick-off, one after."""
    home = Team(name="Arsenal", league="English Premier League", elo_rating=1600)
    away = Team(name="Chelsea", league="English Premier League", elo_rating=1550)
    db_session.add_all([home, away])
    db_session.flush()

    live_kickoff = datetime(2026, 9, 29, 15, 0)
    backtest_kickoff = datetime(2026, 4, 11, 15, 0)
    live = _play(db_session, home, away, live_kickoff, (3, 0))
    backtest = _play(db_session, away, home, backtest_kickoff, (1, 1))
    db_session.add(_prediction(live.id, created_at=datetime(2026, 9, 28, 9, 0)))
    db_session.add(_prediction(backtest.id, created_at=datetime(2026, 10, 1, 9, 0)))
    db_session.commit()


def _rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def test_live_and_backtested_calls_are_counted_apart(db_session):
    _seed(db_session)
    progress = build_progress(db_session)

    assert progress["live"]["record"]["settled"] == 1
    assert progress["backtest"]["record"]["settled"] == 1
    assert progress["overall"]["settled"] == 2


def test_each_month_says_how_much_of_it_was_live(db_session):
    _seed(db_session)
    months = {m["month"]: m for m in build_progress(db_session)["by_month"]}

    assert months["2026-09"]["settled"] == 1
    assert months["2026-09"]["live_settled"] == 1
    assert months["2026-04"]["settled"] == 1
    assert months["2026-04"]["live_settled"] == 0


def test_the_matches_download_has_one_row_per_graded_prediction(client, db_session):
    _seed(db_session)
    response = client.get("/progress/matches.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = _rows(response.text)
    assert len(rows) == 2
    assert {row["record"] for row in rows} == {"live", "backtest"}
    assert {row["outcome"] for row in rows} <= {"won", "lost", "void"}
    # Oldest first, and the teams are names rather than ids.
    assert [row["date"] for row in rows] == ["2026-04-11", "2026-09-29"]
    assert rows[1]["home_team"] == "Arsenal"
    assert rows[1]["call"]


def test_the_downloads_reconcile_with_the_page(client, db_session):
    _seed(db_session)
    progress = build_progress(db_session)
    daily = _rows(client.get("/progress/daily.csv").text)
    matches = _rows(client.get("/progress/matches.csv").text)

    overall = progress["overall"]
    assert sum(int(row["settled"]) for row in daily) == overall["settled"]
    assert sum(int(row["won"]) for row in daily) == overall["won"]
    assert sum(int(row["lost"]) for row in daily) == overall["lost"]
    assert sum(int(row["live_settled"]) for row in daily) == progress["live"]["record"]["settled"]
    assert sum(row["outcome"] == "won" for row in matches) == overall["won"]
    assert sum(row["outcome"] == "lost" for row in matches) == overall["lost"]


def test_a_day_with_nothing_settleable_has_no_win_rate_not_a_zero(client, db_session):
    _seed(db_session)
    daily = _rows(client.get("/progress/daily.csv").text)

    # A rate is only written where something settled; blank is not 0%.
    for row in daily:
        if int(row["settled"]) == 0:
            assert row["win_rate"] == ""
        else:
            assert row["win_rate"] != ""


def test_the_downloads_are_empty_but_well_formed_with_no_predictions(client):
    for path, header in (
        ("/progress/daily.csv", "date,won,lost,void,settled,win_rate,live_settled"),
        ("/progress/matches.csv", "date,competition,home_team,away_team,call,outcome,record"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text.strip() == header
