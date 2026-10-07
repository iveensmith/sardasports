"""Single-market landing pages: Over 2.5 goals and Correct score.

What is worth pinning here is not the arithmetic but the honesty rules the
pages are built on:

* a fixture the engine rates *under* is not a failed over-2.5 call, so it is
  neither listed nor counted;
* the record is every settled call, live and reconstructed kept apart, so a
  page can never read as better than the market it covers;
* every price shown is a bookmaker's where one was stored and a flagged fair
  price otherwise — never a blank, never an unflagged estimate.
"""

from __future__ import annotations

from datetime import datetime

import pytest

import app.services.market_page_service as svc
from app.models import Match, Prediction, Team

TODAY = datetime(2026, 10, 7)


def _stored(over: float, scoreline: str | None = "1-0", probability: float = 0.15) -> Prediction:
    return Prediction(
        match_id=0,
        prob_home=50.0,
        prob_draw=25.0,
        prob_away=25.0,
        expected_goals_home=1.5,
        expected_goals_away=1.0,
        top_scorelines=[{"score": scoreline, "probability": probability}] if scoreline else [],
        prob_btts_yes=50.0,
        prob_btts_no=50.0,
        goals_markets=[
            {"line": 2.5, "prob_over": over, "prob_under": 100.0 - over, "model_used": True}
        ],
        ht_goals_markets=[],
        corners_markets=[],
        cards_markets=[],
        confidence=90.0,
    )


@pytest.fixture
def teams(db_session):
    home = Team(name="Arsenal", league="English Premier League", elo_rating=1600)
    away = Team(name="Chelsea", league="English Premier League", elo_rating=1550)
    db_session.add_all([home, away])
    db_session.flush()
    return home, away


def _played(db_session, teams, when, score, *, over, scoreline="1-0", created=None):
    home, away = teams
    match = Match(
        match_date=when,
        competition="English Premier League",
        season="2026-2027",
        home_team_id=home.id,
        away_team_id=away.id,
        status="completed",
        home_score=score[0],
        away_score=score[1],
    )
    db_session.add(match)
    db_session.flush()
    prediction = _stored(over, scoreline)
    prediction.match_id = match.id
    prediction.created_at = created or datetime(when.year, when.month, when.day, 9, 0)
    db_session.add(prediction)
    db_session.commit()
    return match


# --- reading a prediction ---------------------------------------------------------------


def test_the_over_probability_is_read_from_the_2_5_line_only():
    prediction = {
        "goals_markets": [
            {"line": 1.5, "prob_over": 80.0},
            {"line": 2.5, "prob_over": 55.5},
        ]
    }
    assert svc._over_probability(prediction) == 55.5
    assert svc._over_probability({"goals_markets": [{"line": 1.5, "prob_over": 80.0}]}) is None
    assert svc._over_probability(None) is None


def test_the_likeliest_scoreline_is_returned_as_a_percentage():
    assert svc._top_scoreline({"top_scorelines": [{"score": "2-1", "probability": 0.1273}]}) == (
        "2-1",
        12.7,
    )


def test_an_older_bare_string_scoreline_has_no_probability_and_is_not_used():
    """The first stored shape was a list of "2-1" strings. With no probability
    there is nothing honest to print beside it, so it is skipped, not guessed."""
    assert svc._top_scoreline({"top_scorelines": ["2-1", "1-0"]}) is None
    assert svc._top_scoreline({"top_scorelines": []}) is None


# --- every pick has a price, and says where it came from ---------------------------------


def test_a_quoted_over_2_5_price_is_used_as_is():
    prediction = {"goals_markets": [{"line": 2.5, "prob_over": 60.0}]}
    pick = svc._pick("over-2-5", prediction, {"goals": {"over_2.5": 1.85}})
    assert pick["odds"] == pytest.approx(1.85)
    assert pick["odds_is_estimated"] is False


def test_an_unquoted_over_2_5_price_falls_back_to_a_flagged_fair_price():
    prediction = {"goals_markets": [{"line": 2.5, "prob_over": 60.0}]}
    pick = svc._pick("over-2-5", prediction, None)
    assert pick["odds"] == pytest.approx(1.67)
    assert pick["odds_is_estimated"] is True


def test_correct_score_is_always_a_flagged_fair_price():
    prediction = {"top_scorelines": [{"score": "1-0", "probability": 0.125}]}
    pick = svc._pick("correct-score", prediction, {"goals": {"over_2.5": 1.85}})
    assert pick["label"] == "1-0"
    assert pick["probability"] == 12.5
    assert pick["odds"] == pytest.approx(8.0)
    assert pick["odds_is_estimated"] is True


def test_a_fixture_with_no_view_on_the_market_yields_no_pick():
    assert svc._pick("over-2-5", {"goals_markets": []}, None) is None
    assert svc._pick("correct-score", {"top_scorelines": []}, None) is None


# --- the record -------------------------------------------------------------------------


def test_over_2_5_counts_only_calls_where_the_engine_leaned_over(db_session, teams):
    _played(db_session, teams, datetime(2026, 10, 1, 15), (2, 2), over=70.0)  # leaned over, landed
    _played(db_session, teams, datetime(2026, 10, 2, 15), (1, 0), over=65.0)  # leaned over, missed
    _played(db_session, teams, datetime(2026, 10, 3, 15), (3, 1), over=30.0)  # leaned under

    record = svc._record(db_session, "over-2-5", TODAY)

    assert record["overall"]["settled"] == 2
    assert record["overall"]["won"] == 1
    assert record["overall"]["rate"] == 50.0


def test_live_and_reconstructed_calls_are_counted_apart(db_session, teams):
    kickoff = datetime(2026, 10, 1, 15)
    _played(db_session, teams, kickoff, (2, 2), over=70.0, created=datetime(2026, 10, 1, 9))  # live
    _played(
        db_session,
        teams,
        datetime(2026, 10, 2, 15),
        (0, 0),
        over=70.0,
        created=datetime(2026, 10, 5),
    )  # stored after the match

    record = svc._record(db_session, "over-2-5", TODAY)

    assert record["live"] == {"settled": 1, "won": 1, "rate": 100.0}
    assert record["backtest"] == {"settled": 1, "won": 0, "rate": 0.0}
    assert record["overall"]["settled"] == 2


def test_the_window_excludes_old_matches_and_the_target_day_itself(db_session, teams):
    _played(db_session, teams, datetime(2026, 8, 1, 15), (2, 2), over=70.0)  # 67 days back
    _played(db_session, teams, datetime(2026, 10, 7, 15), (2, 2), over=70.0)  # the day itself

    assert svc._record(db_session, "over-2-5", TODAY)["overall"]["settled"] == 0


def test_correct_score_counts_every_settled_call_not_just_the_hits(db_session, teams):
    _played(db_session, teams, datetime(2026, 10, 1, 15), (1, 0), over=50.0, scoreline="1-0")
    _played(db_session, teams, datetime(2026, 10, 2, 15), (3, 2), over=50.0, scoreline="1-0")
    _played(db_session, teams, datetime(2026, 10, 3, 15), (0, 0), over=50.0, scoreline="1-1")

    record = svc._record(db_session, "correct-score", TODAY)

    assert record["overall"] == {"settled": 3, "won": 1, "rate": 33.3}
    # Only the hit is listed, and the list never feeds back into the rate.
    assert [h["pick"] for h in record["recent_hits"]] == ["1-0"]


def test_a_stored_prediction_without_a_usable_scoreline_is_not_counted(db_session, teams):
    _played(db_session, teams, datetime(2026, 10, 1, 15), (1, 0), over=50.0, scoreline=None)

    assert svc._record(db_session, "correct-score", TODAY)["overall"]["settled"] == 0


def test_an_empty_record_has_no_rate_rather_than_zero(db_session, teams):
    record = svc._record(db_session, "over-2-5", TODAY)
    assert record["overall"] == {"settled": 0, "won": 0, "rate": None}
    assert record["recent_hits"] == []


# --- the day's page ----------------------------------------------------------------------


def _fixture(db_session, teams, when, *, status="scheduled", score=None):
    home, away = teams
    match = Match(
        match_date=when,
        competition="English Premier League",
        season="2026-2027",
        home_team_id=home.id,
        away_team_id=away.id,
        status=status,
        home_score=None if score is None else score[0],
        away_score=None if score is None else score[1],
    )
    db_session.add(match)
    db_session.flush()
    return match


def _prediction(over: float, scoreline: str = "1-0", probability: float = 0.15) -> dict:
    return {
        "home_win": 50.0,
        "draw": 25.0,
        "away_win": 25.0,
        "btts_yes": 50.0,
        "btts_no": 50.0,
        "goals_markets": [{"line": 2.5, "prob_over": over, "prob_under": 100 - over}],
        "top_scorelines": [{"score": scoreline, "probability": probability}],
        "confidence": 90.0,
    }


def test_the_day_lists_only_over_leaning_fixtures_best_first(db_session, teams, monkeypatch):
    weak = _fixture(db_session, teams, datetime(2026, 10, 7, 15))
    strong = _fixture(db_session, teams, datetime(2026, 10, 7, 17))
    under = _fixture(db_session, teams, datetime(2026, 10, 7, 19))
    db_session.commit()
    by_id = {weak.id: _prediction(52.0), strong.id: _prediction(71.0), under.id: _prediction(34.0)}
    monkeypatch.setattr(
        svc, "predict_for_matches", lambda session, matches: [by_id[m.id] for m in matches]
    )

    page = svc.build_market_page(db_session, "over-2-5", TODAY)

    assert [p["pick"]["probability"] for p in page["picks"]] == [71.0, 52.0]
    assert page["fixtures"] == 3
    assert page["considered"] == 3  # the under-leaning one was weighed, then not listed
    assert all(p["pick"]["odds"] is not None for p in page["picks"])
    assert all(p["pick"]["outcome"] is None for p in page["picks"])


def test_a_played_fixture_on_the_day_is_graded(db_session, teams, monkeypatch):
    played = _fixture(
        db_session, teams, datetime(2026, 10, 7, 12), status="completed", score=(2, 1)
    )
    db_session.commit()
    monkeypatch.setattr(svc, "predict_for_matches", lambda session, matches: [_prediction(66.0)])

    page = svc.build_market_page(db_session, "over-2-5", TODAY)

    assert page["picks"][0]["match_id"] == played.id
    assert page["picks"][0]["pick"]["outcome"] == "won"
    assert page["picks"][0]["score"] == {"home": 2, "away": 1}


def test_a_fixture_the_engine_could_not_price_is_left_out_not_failed(
    db_session, teams, monkeypatch
):
    _fixture(db_session, teams, datetime(2026, 10, 7, 15))
    db_session.commit()
    monkeypatch.setattr(svc, "predict_for_matches", lambda session, matches: [None])

    page = svc.build_market_page(db_session, "correct-score", TODAY)

    assert page["picks"] == []
    assert page["considered"] == 0
    assert page["fixtures"] == 1


def test_correct_score_picks_carry_no_base_rate(db_session, teams, monkeypatch):
    monkeypatch.setattr(svc, "predict_for_matches", lambda session, matches: [])
    assert svc.build_market_page(db_session, "correct-score", TODAY)["base_rate"] is None


def test_an_unknown_market_page_is_a_404(client):
    assert client.get("/markets/not-a-market").status_code == 404
