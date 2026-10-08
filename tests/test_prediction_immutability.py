"""A prediction stored before kick-off is final once the match is under way.

The track record calls a prediction *live* when it was stored before kick-off
(`Prediction.created_at < Match.match_date`). That test only means something
if the row cannot change afterwards: `created_at` survives an overwrite, so a
recompute after kick-off used to be able to swap the numbers under a stored
call and still count as one published in advance.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

import app.services.prediction_service as prediction_service
from app.models import Match, Prediction, PredictionHistory, Team
from app.services.prediction_service import _persist_prediction, predict_for_match
from app.services.progress_service import build_progress


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _result(home: float = 62.0, draw: float = 22.0, away: float = 16.0) -> SimpleNamespace:
    """The fields `_persist_prediction` reads, in the shape the engine returns."""
    return SimpleNamespace(
        home_win=home,
        draw=draw,
        away_win=away,
        expected_goals_home=2.1,
        expected_goals_away=0.9,
        top_scorelines=["2-0", "2-1"],
        prob_btts_yes=44.0,
        prob_btts_no=56.0,
        goals_markets=[{"line": 2.5, "prob_over": 55.0, "prob_under": 45.0, "model_used": False}],
        ht_goals_markets=[],
        corners_markets=[],
        cards_markets=[],
        confidence=90.0,
        confidence_label="Very High",
    )


def _teams(db_session) -> tuple[Team, Team]:
    teams = []
    for name, elo in (("Arsenal", 1600), ("Chelsea", 1550)):
        team = db_session.query(Team).filter(Team.name == name).one_or_none()
        if team is None:
            team = Team(name=name, league="English Premier League", elo_rating=elo)
            db_session.add(team)
            db_session.flush()
        teams.append(team)
    return teams[0], teams[1]


def _match(db_session, kickoff: datetime, status: str = "scheduled", score=None) -> Match:
    home, away = _teams(db_session)
    match = Match(
        match_date=kickoff,
        competition="English Premier League",
        season="2026-2027",
        home_team_id=home.id,
        away_team_id=away.id,
        status=status,
        home_score=score[0] if score else None,
        away_score=score[1] if score else None,
    )
    db_session.add(match)
    db_session.commit()
    return match


def _stored(db_session, match: Match) -> Prediction:
    db_session.expire_all()
    return db_session.query(Prediction).filter(Prediction.match_id == match.id).one()


def _history_count(db_session, match: Match) -> int:
    return (
        db_session.query(PredictionHistory).filter(PredictionHistory.match_id == match.id).count()
    )


def _kick_off(db_session, match: Match, score=(3, 0)) -> None:
    """Play the match, as the fixture refresh would: the stored row is left as it is,
    backdated so it reads as stored a day before the (now past) kick-off."""
    match.match_date = _now() - timedelta(hours=3)
    match.status = "completed"
    match.home_score, match.away_score = score
    prediction = db_session.query(Prediction).filter(Prediction.match_id == match.id).one()
    prediction.created_at = match.match_date - timedelta(days=1)
    db_session.commit()


def test_a_prediction_stored_before_kick_off_is_unchanged_by_a_later_recompute(db_session):
    match = _match(db_session, _now() + timedelta(days=1))
    _persist_prediction(db_session, match, _result(home=62.0), None)
    _kick_off(db_session, match)
    before = _stored(db_session, match)
    created_at, updated_at = before.created_at, before.updated_at

    # A retrained model now disagrees, and the board is viewed after the match.
    _persist_prediction(db_session, match, _result(home=10.0, draw=20.0, away=70.0), None)

    after = _stored(db_session, match)
    assert after.prob_home == pytest.approx(0.62)
    assert after.prob_away == pytest.approx(0.16)
    assert after.created_at == created_at
    assert after.updated_at == updated_at
    # No hindsight snapshot is appended to the timeline either.
    assert _history_count(db_session, match) == 1


def test_a_match_past_its_kick_off_is_frozen_even_if_not_marked_completed(db_session):
    """The fixture feed can lag the clock; kick-off is a time, not a status."""
    match = _match(db_session, _now() + timedelta(days=1))
    _persist_prediction(db_session, match, _result(home=62.0), None)
    match.match_date = _now() - timedelta(minutes=5)
    db_session.commit()

    _persist_prediction(db_session, match, _result(home=10.0, draw=20.0, away=70.0), None)

    assert _stored(db_session, match).prob_home == pytest.approx(0.62)
    assert _history_count(db_session, match) == 1


def test_a_prediction_stored_before_kick_off_can_still_move_before_kick_off(db_session):
    match = _match(db_session, _now() + timedelta(days=1))
    _persist_prediction(db_session, match, _result(home=62.0), None)

    _persist_prediction(db_session, match, _result(home=55.0, draw=25.0, away=20.0), None)

    assert _stored(db_session, match).prob_home == pytest.approx(0.55)
    # The timeline keeps both snapshots.
    assert _history_count(db_session, match) == 2


def test_a_played_match_with_no_stored_prediction_gets_a_backtest_row(db_session):
    """This is how the reconstructed record is built, so it must keep working."""
    match = _match(db_session, _now() - timedelta(days=30), status="completed", score=(2, 1))

    served = predict_for_match(db_session, match.id)

    row = _stored(db_session, match)
    assert row.created_at > match.match_date
    assert _history_count(db_session, match) == 1
    assert served["match_id"] == match.id

    progress = build_progress(db_session)
    assert progress["backtest"]["record"]["settled"] == 1
    assert progress["live"]["record"]["settled"] == 0


def test_serving_after_kick_off_returns_the_stored_prediction_without_recomputing(
    db_session, monkeypatch
):
    match = _match(db_session, _now() + timedelta(days=1))
    _persist_prediction(db_session, match, _result(home=62.0, draw=22.0, away=16.0), None)
    _kick_off(db_session, match)

    def _no_recompute(*args, **kwargs):
        raise AssertionError("a started match with a stored prediction must not be recomputed")

    monkeypatch.setattr(prediction_service, "predict_match", _no_recompute)
    monkeypatch.setattr(prediction_service, "_all_completed_history", _no_recompute)

    served = predict_for_match(db_session, match.id)

    assert served["home_win"] == 62.0
    assert served["draw"] == 22.0
    assert served["away_win"] == 16.0
    assert served["btts_yes"] == 44.0
    assert served["confidence"] == 90.0
    assert served["home_team"] == "Arsenal"
    # What the row never recorded is empty, not re-derived from today's engine.
    assert served["estimator_probs"] == {}
    assert served["explanation"] is None
    assert served["btts_model_used"] is None


def test_the_record_does_not_change_when_a_played_match_is_recomputed(db_session):
    # One call stored before kick-off (live), one reconstructed afterwards.
    live_match = _match(db_session, _now() + timedelta(days=1))
    _persist_prediction(db_session, live_match, _result(home=62.0), None)
    _kick_off(db_session, live_match, score=(3, 0))
    backtest_match = _match(db_session, _now() - timedelta(days=30), "completed", score=(0, 2))
    predict_for_match(db_session, backtest_match.id)

    def snapshot() -> dict:
        progress = build_progress(db_session)
        progress.pop("generated_at")
        return progress

    before = snapshot()
    assert before["live"]["record"]["settled"] == 1
    assert before["backtest"]["record"]["settled"] == 1

    for match in (live_match, backtest_match):
        # Both the serving path and a direct persist, with numbers that would
        # flip the headline call if they were ever allowed to land.
        predict_for_match(db_session, match.id)
        _persist_prediction(db_session, match, _result(home=5.0, draw=15.0, away=80.0), None)

    assert snapshot() == before
