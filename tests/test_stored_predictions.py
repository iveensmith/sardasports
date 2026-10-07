"""Stored predictions: the scale they are read at, the fallback, and the results strip.

Three things here have each failed in production in some form, which is why they
are pinned:

* the 1X2 and BTTS probabilities are stored as fractions and everything that
  ranks calls works in percentages; reading them raw made match-result picks
  unable to lead in the track record;
* a failed live prediction left a board row blank, so a card read as having no
  trained model;
* the home page's results strip depended on one calendar day having enough
  finished matches, fetched through a full board recomputation, and vanished.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import app.services.recent_results as recent_module
import app.services.stored_predictions as stored
from app.models import Match, Prediction, Team
from app.services.recent_results import clear_cache, recent_settled
from app.services.stored_predictions import payload_from_stored, predict_with_stored_fallback
from ml.markets import candidate_calls


def _row(match_id: int, *, home=0.62, draw=0.22, away=0.16) -> Prediction:
    return Prediction(
        match_id=match_id,
        prob_home=home,
        prob_draw=draw,
        prob_away=away,
        expected_goals_home=1.8,
        expected_goals_away=0.9,
        top_scorelines=[{"score": "2-0", "probability": 0.14}],
        prob_btts_yes=0.44,
        prob_btts_no=0.56,
        goals_markets=[{"line": 2.5, "prob_over": 55.0, "prob_under": 45.0, "model_used": True}],
        ht_goals_markets=[],
        corners_markets=[],
        cards_markets=[],
        confidence=88.0,
        confidence_label="High",
    )


@pytest.fixture(autouse=True)
def _fresh_strip_cache():
    """The strip keeps its last good answer in memory; tests must not share it."""
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def teams(db_session):
    pair = [
        Team(name="Arsenal", league="English Premier League", elo_rating=1600),
        Team(name="Chelsea", league="English Premier League", elo_rating=1550),
    ]
    db_session.add_all(pair)
    db_session.flush()
    return pair


def _match(db_session, teams, when, score=None, sport="football") -> Match:
    match = Match(
        match_date=when,
        competition="English Premier League",
        season="2026-2027",
        sport=sport,
        home_team_id=teams[0].id,
        away_team_id=teams[1].id,
        status="completed" if score else "scheduled",
        home_score=None if score is None else score[0],
        away_score=None if score is None else score[1],
    )
    db_session.add(match)
    db_session.flush()
    return match


# --- the scale ------------------------------------------------------------------------------


def test_stored_fractions_are_read_back_as_percentages(db_session, teams):
    match = _match(db_session, teams, datetime(2026, 10, 1, 15), (2, 0))
    row = _row(match.id)
    db_session.add(row)
    db_session.commit()

    payload = payload_from_stored(row)

    assert payload["home_win"] == pytest.approx(62.0)
    assert payload["draw"] == pytest.approx(22.0)
    assert payload["btts_yes"] == pytest.approx(44.0)
    # The over/under lines are already stored as percentages and are left alone.
    assert payload["goals_markets"][0]["prob_over"] == 55.0


def test_a_match_result_call_is_on_the_same_scale_as_every_other_market(db_session, teams):
    """The regression: with the fractions unconverted, a 62% home win ranked at 0.62
    against a 55% over 2.5, so it could never lead."""
    match = _match(db_session, teams, datetime(2026, 10, 1, 15), (2, 0))
    row = _row(match.id)
    db_session.add(row)
    db_session.commit()

    calls = {c.key: c.probability for c in candidate_calls(payload_from_stored(row))}

    assert calls["match_result:home"] == pytest.approx(62.0)
    assert calls["goals:over_2.5"] == pytest.approx(55.0)
    assert calls["match_result:home"] > calls["goals:over_2.5"]


def test_a_missing_probability_stays_missing_rather_than_becoming_zero():
    row = _row(1)
    row.prob_btts_yes = None
    assert payload_from_stored(row)["btts_yes"] is None


# --- falling back to a stored prediction -------------------------------------------------------


def test_a_failed_live_prediction_falls_back_to_the_stored_one(db_session, teams, monkeypatch):
    match = _match(db_session, teams, datetime(2026, 10, 8, 15))
    db_session.add(_row(match.id))
    db_session.commit()
    monkeypatch.setattr(stored, "predict_for_matches", lambda session, matches: [None])

    [result] = predict_with_stored_fallback(db_session, [match])

    assert result is not None
    assert result["home_win"] == pytest.approx(62.0)


def test_a_live_prediction_is_never_replaced_by_a_stored_one(db_session, teams, monkeypatch):
    match = _match(db_session, teams, datetime(2026, 10, 8, 15))
    db_session.add(_row(match.id))
    db_session.commit()
    live = {"home_win": 40.0, "draw": 30.0, "away_win": 30.0}
    monkeypatch.setattr(stored, "predict_for_matches", lambda session, matches: [live])

    assert predict_with_stored_fallback(db_session, [match]) == [live]


def test_nothing_stored_and_nothing_live_stays_unpredicted(db_session, teams, monkeypatch):
    match = _match(db_session, teams, datetime(2026, 10, 8, 15))
    db_session.commit()
    monkeypatch.setattr(stored, "predict_for_matches", lambda session, matches: [None])

    assert predict_with_stored_fallback(db_session, [match]) == [None]


def test_only_football_falls_back_because_the_stored_columns_are_footballs(
    db_session, teams, monkeypatch
):
    match = _match(db_session, teams, datetime(2026, 10, 8, 15), sport="basketball")
    db_session.add(_row(match.id))
    db_session.commit()
    monkeypatch.setattr(stored, "predict_for_matches", lambda session, matches: [None])

    assert predict_with_stored_fallback(db_session, [match]) == [None]


# --- the results strip ------------------------------------------------------------------------


def _settled_run(db_session, teams, days: int):
    """One graded match per day for `days` days, newest on 2026-10-06."""
    for i in range(days):
        when = datetime(2026, 10, 6, 15) - timedelta(days=i)
        match = _match(db_session, teams, when, (2, 0))
        db_session.add(_row(match.id))
    db_session.commit()


def test_the_strip_spans_days_instead_of_needing_one_busy_day(db_session, teams):
    """One match a day is exactly the shape that used to make the strip vanish."""
    _settled_run(db_session, teams, 6)

    result = recent_settled(db_session, limit=24)

    assert result["count"] == 6
    assert result["from"] == "2026-10-01"
    assert result["to"] == "2026-10-06"


def test_the_strip_is_newest_first_and_only_graded_picks(db_session, teams):
    _settled_run(db_session, teams, 5)
    unplayed = _match(db_session, teams, datetime(2026, 10, 9, 15))
    db_session.add(_row(unplayed.id))
    db_session.commit()

    rows = recent_settled(db_session)["rows"]

    assert [r["match_date"][:10] for r in rows] == sorted(
        (r["match_date"][:10] for r in rows), reverse=True
    )
    assert all(r["best_tip"]["outcome"] in ("won", "lost") for r in rows)
    assert all(r["score"] is not None for r in rows)  # the unplayed fixture is excluded


def test_the_limit_is_respected(db_session, teams):
    _settled_run(db_session, teams, 8)
    assert recent_settled(db_session, limit=3)["count"] == 3


def test_the_strip_reads_stored_predictions_and_never_recomputes(db_session, teams, monkeypatch):
    """It must keep working when live prediction is failing, which is when it vanished."""
    import app.services.prediction_service as prediction_service

    def boom(*args, **kwargs):
        raise AssertionError("the results strip must not run a live prediction")

    monkeypatch.setattr(prediction_service, "predict_for_matches", boom)
    monkeypatch.setattr(stored, "predict_for_matches", boom)
    _settled_run(db_session, teams, 5)

    assert recent_settled(db_session)["count"] == 5


def test_with_no_settled_picks_the_strip_is_empty_not_an_error(db_session):
    result = recent_settled(db_session)
    assert result == {"count": 0, "won": 0, "from": None, "to": None, "rows": []}


def test_the_won_count_agrees_with_the_rows(db_session, teams):
    _settled_run(db_session, teams, 5)
    result = recent_settled(db_session)
    assert result["won"] == sum(1 for r in result["rows"] if r["best_tip"]["outcome"] == "won")


def test_the_endpoint_serves_it_and_validates_the_limit(client, db_session, teams):
    _settled_run(db_session, teams, 4)

    ok = client.get("/board/recent-settled?limit=10")
    assert ok.status_code == 200
    assert ok.json()["count"] == 4
    assert client.get("/board/recent-settled?limit=0").status_code == 422
    assert client.get("/board/recent-settled?limit=9999").status_code == 422


# --- the strip survives a failing database -------------------------------------------------------


def test_a_second_call_within_the_ttl_does_not_touch_the_database(db_session, teams, monkeypatch):
    _settled_run(db_session, teams, 5)
    first = recent_settled(db_session)

    def boom(*args, **kwargs):
        raise AssertionError("served from memory, so no query should run")

    monkeypatch.setattr(recent_module, "_compute", boom)

    assert recent_settled(db_session) is first


def test_when_the_recompute_fails_the_last_good_answer_is_served_not_an_error(
    db_session, teams, monkeypatch
):
    _settled_run(db_session, teams, 5)
    good = recent_settled(db_session)
    # Past the freshness window, so the next call tries to recompute.
    monkeypatch.setattr(recent_module, "CACHE_TTL_SECONDS", -1)

    def locked(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(recent_module, "_compute", locked)

    again = recent_settled(db_session)

    assert again["count"] == good["count"] == 5
    assert again["stale"] is True
    assert again["rows"] == good["rows"]


def test_a_stale_answer_is_replaced_once_the_database_recovers(db_session, teams, monkeypatch):
    _settled_run(db_session, teams, 5)
    recent_settled(db_session)
    monkeypatch.setattr(recent_module, "CACHE_TTL_SECONDS", -1)
    real = recent_module._compute

    monkeypatch.setattr(
        recent_module, "_compute", lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
    )
    assert recent_settled(db_session)["stale"] is True

    monkeypatch.setattr(recent_module, "_compute", real)
    fresh = recent_settled(db_session)

    assert "stale" not in fresh


def test_with_no_good_answer_ever_a_failure_is_an_error_not_an_empty_strip(db_session, monkeypatch):
    """An empty 200 would be cached by the website for minutes and hide the strip;
    an error is not cached, and the website falls back on its own copy."""

    def locked(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(recent_module, "_compute", locked)

    with pytest.raises(RuntimeError):
        recent_settled(db_session)


def test_each_limit_has_its_own_cached_answer(db_session, teams):
    _settled_run(db_session, teams, 6)

    assert recent_settled(db_session, limit=2)["count"] == 2
    assert recent_settled(db_session, limit=6)["count"] == 6


# --- the canary ---------------------------------------------------------------------------------


def test_the_canary_rebuilds_the_strip_so_a_visitor_finds_it_fresh(db_session, teams, monkeypatch):
    import app.scheduler as scheduler

    _settled_run(db_session, teams, 6)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    scheduler.strip_canary_job()

    # Served from memory now: a query here would blow up.
    def boom(*args, **kwargs):
        raise AssertionError("the canary should already have filled the cache")

    monkeypatch.setattr(recent_module, "_compute", boom)
    assert recent_settled(db_session)["count"] == 6


def test_the_canary_logs_an_error_when_too_few_picks_are_graded(
    db_session, teams, monkeypatch, caplog
):
    import app.scheduler as scheduler

    _settled_run(db_session, teams, 2)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    with caplog.at_level("ERROR"):
        scheduler.strip_canary_job()

    assert "strip canary" in caplog.text
    assert "only 2 graded picks" in caplog.text


def test_the_canary_reports_a_failure_and_never_raises(db_session, monkeypatch, caplog):
    import app.scheduler as scheduler

    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(
        recent_module, "_compute", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("locked"))
    )

    with caplog.at_level("ERROR"):
        scheduler.strip_canary_job()  # must not raise

    assert "could not rebuild" in caplog.text
