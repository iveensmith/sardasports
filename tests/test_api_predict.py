"""Tests for GET /predict/{match_id} — Elo + Poisson ensemble (no XGBoost model trained)."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models import Match, Team


def approx100(value: float, tol: float = 0.5):
    return pytest.approx(value, abs=tol)


def _seed_league(db_session):
    arsenal = Team(name="Arsenal", league="English Premier League", elo_rating=1500)
    chelsea = Team(name="Chelsea", league="English Premier League", elo_rating=1500)
    everton = Team(name="Everton", league="English Premier League", elo_rating=1500)
    db_session.add_all([arsenal, chelsea, everton])
    db_session.flush()

    completed = [
        Match(
            match_date=datetime(2024, 1, 1),
            competition="English Premier League",
            season="2023-2024",
            home_team_id=arsenal.id,
            away_team_id=everton.id,
            home_score=3,
            away_score=0,
            status="completed",
        ),
        Match(
            match_date=datetime(2024, 1, 8),
            competition="English Premier League",
            season="2023-2024",
            home_team_id=chelsea.id,
            away_team_id=everton.id,
            home_score=1,
            away_score=1,
            status="completed",
        ),
        Match(
            match_date=datetime(2024, 1, 15),
            competition="English Premier League",
            season="2023-2024",
            home_team_id=everton.id,
            away_team_id=arsenal.id,
            home_score=0,
            away_score=2,
            status="completed",
        ),
    ]
    db_session.add_all(completed)

    fixture = Match(
        match_date=datetime(2024, 2, 1),
        competition="English Premier League",
        season="2023-2024",
        home_team_id=arsenal.id,
        away_team_id=chelsea.id,
        status="scheduled",
    )
    db_session.add(fixture)
    db_session.commit()
    return fixture


def test_predict_returns_a_full_valid_ensemble_payload(client, db_session):
    fixture = _seed_league(db_session)

    response = client.get(f"/predict/{fixture.id}")
    assert response.status_code == 200
    body = response.json()

    assert body["home_team"] == "Arsenal"
    assert body["away_team"] == "Chelsea"

    # Result probabilities are real percentages that sum to ~100.
    total = body["home_win"] + body["draw"] + body["away_win"]
    assert total == approx100(100.0)

    assert 0 <= body["confidence"] <= 100
    assert body["confidence_label"] in {"Low", "Medium", "High", "Very High"}
    assert len(body["top_scorelines"]) == 5
    assert body["btts_yes"] + body["btts_no"] == approx100(100.0)
    # No models have been trained yet in this test DB, so the ensemble should
    # fall back to Elo + Poisson only (no "xgboost" weight used), and the
    # dedicated BTTS model is reported as unused.
    assert "xgboost" not in body["model_weights_used"]
    assert body["btts_model_used"] is False
    assert body["explanation"] is None
    # _seed_league's matches carry real home_score/away_score, so goals_markets
    # (which reuses the main Poisson fit, always available when any goals
    # exist) must be genuinely available — real numbers, just no dedicated
    # model (none trained in this test DB).
    assert len(body["goals_markets"]) == 2  # 1.5, 2.5
    for market in body["goals_markets"]:
        assert market["prob_over"] + market["prob_under"] == approx100(100.0)
        assert market["model_used"] is False
    # But the same fixtures carry no half-time/corners/cards data at all, so
    # every offered line of those three markets must report genuinely
    # unavailable (None), not a fabricated number, and "model_used" must be
    # False even if a model happened to be trained (it wasn't here) — there's
    # no Poisson baseline to blend it with.
    assert len(body["ht_goals_markets"]) == 1  # 0.5
    assert len(body["corners_markets"]) == 3  # 7.5, 8.5, 9.5
    assert len(body["cards_markets"]) == 3  # 2.5, 3.5, 4.5
    for market in body["ht_goals_markets"] + body["corners_markets"] + body["cards_markets"]:
        assert market["prob_over"] is None
        assert market["prob_under"] is None
        assert market["model_used"] is False


def test_predict_unknown_match_returns_404(client):
    response = client.get("/predict/999999")
    assert response.status_code == 404


def test_predict_is_deterministic_across_repeated_calls(client, db_session):
    # Redis is disabled in the test environment (REDIS_URL=""), so this
    # exercises the "no cache" path — recomputing from the same DB state
    # must still produce the same probabilities every time.
    fixture = _seed_league(db_session)
    first = client.get(f"/predict/{fixture.id}").json()
    second = client.get(f"/predict/{fixture.id}").json()
    assert first["home_win"] == second["home_win"]
    assert first["draw"] == second["draw"]
    assert first["away_win"] == second["away_win"]


def test_predict_does_not_crash_with_zero_prior_history(client, db_session):
    """Regression test: the very first match ever ingested (or a brand-new
    league with no completed matches yet) must not crash /predict — the
    Poisson model has no history to fit from and should fall back to its
    default league-average parameters instead of raising."""
    home = Team(name="Brand New FC")
    away = Team(name="Also New FC")
    db_session.add_all([home, away])
    db_session.flush()

    fixture = Match(
        match_date=datetime(2024, 1, 1),
        competition="New League",
        season="2023-2024",
        home_team_id=home.id,
        away_team_id=away.id,
        status="scheduled",
    )
    db_session.add(fixture)
    db_session.commit()

    response = client.get(f"/predict/{fixture.id}")
    assert response.status_code == 200
    body = response.json()
    total = body["home_win"] + body["draw"] + body["away_win"]
    assert total == approx100(100.0)


def test_a_football_prediction_carries_calls_for_every_market(client, db_session):
    """Regression: football is the route's fall-through branch.

    `predict_for_match` returns no `sport` key for football at all —
    `PredictionOut.sport` supplies the default on serialisation. So a branch
    written as `if sport == "football"` is never true, and the calls silently
    came back null while the board (which reads `match.sport` off the ORM row)
    had them. Two endpoints disagreeing about the same fixture again.
    """
    from datetime import datetime, timedelta

    from app.models import Match, Team

    home = Team(name="Calls Home", league="Test League", sport="football")
    away = Team(name="Calls Away", league="Test League", sport="football")
    db_session.add_all([home, away])
    db_session.flush()

    start = datetime(2024, 1, 1)
    for index in range(250):
        db_session.add(
            Match(
                external_id=f"calls-{index}",
                match_date=start + timedelta(days=index),
                competition="Test League",
                season="2024",
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=2,
                away_score=1,
                status="completed",
                sport="football",
            )
        )
    upcoming = Match(
        external_id="calls-upcoming",
        match_date=start + timedelta(days=400),
        competition="Test League",
        season="2024",
        home_team_id=home.id,
        away_team_id=away.id,
        status="scheduled",
        sport="football",
    )
    db_session.add(upcoming)
    db_session.commit()
    match_id = upcoming.id

    from app.services.base_rates import reset_cache

    reset_cache()
    try:
        body = client.get(f"/predict/{match_id}").json()
    finally:
        reset_cache()

    assert body.get("calls") is not None, "football predictions must carry calls"
    assert body["calls"]["headline"] is not None
    markets = {call["market"] for call in body["calls"]["by_market"]}
    # More than the match result, which is the entire point.
    assert "match_result" in markets
    assert len(markets) > 1
    for call in body["calls"]["by_market"]:
        assert 0.0 <= call["probability"] <= 100.0
