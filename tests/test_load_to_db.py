"""Tests for how the CSV loader meets fixtures the API already ingested.

The same fixture can reach the database twice: once from the API with an
`apif-` id and a kick-off time, once from a Football-Data.co.uk CSV with a hash
id and a bare date. The loader recognises matches by `external_id` alone, so
without reconciliation the second arrival is inserted as a duplicate — and the
original, which owns the predictions made before kick-off, never completes.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.models import Match, Prediction, Team
from scripts.load_to_db import load_matches

COMPETITION = "Spanish Segunda Division"


def _row(**overrides) -> dict:
    row = {
        "external_id": "csv-1",
        "match_date": "2026-09-28",
        "competition": COMPETITION,
        "season": "2026-2027",
        "neutral_venue": False,
        "home_team": "Leganes",
        "away_team": "Castellon",
        "home_score": 2,
        "away_score": 1,
        "home_ht_goals": 1,
        "away_ht_goals": 0,
        "home_shots": 14,
        "away_shots": 9,
        "home_shots_on_target": 6,
        "away_shots_on_target": 3,
        "home_corners": 7,
        "away_corners": 4,
        "home_yellow_cards": 2,
        "away_yellow_cards": 3,
        "home_red_cards": 0,
        "away_red_cards": 0,
        "referee": None,
        "odds_home_win": 2.1,
        "odds_draw": 3.2,
        "odds_away_win": 3.4,
    }
    row.update(overrides)
    return row


def _frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _api_fixture(
    db_session, when: datetime, status: str = "scheduled", competition: str = COMPETITION
) -> Match:
    home = Team(name="Leganes", league=COMPETITION, elo_rating=1500)
    away = Team(name="Castellon", league=COMPETITION, elo_rating=1500)
    db_session.add_all([home, away])
    db_session.flush()
    match = Match(
        external_id="apif-12345",
        match_date=when,
        competition=competition,
        season="2026-2027",
        home_team_id=home.id,
        away_team_id=away.id,
        status=status,
        home_score=0 if status == "completed" else None,
        away_score=0 if status == "completed" else None,
    )
    db_session.add(match)
    db_session.flush()
    return match


def _predict(db_session, match: Match) -> None:
    db_session.add(
        Prediction(
            match_id=match.id,
            prob_home=50.0,
            prob_draw=25.0,
            prob_away=25.0,
            expected_goals_home=1.5,
            expected_goals_away=1.0,
            top_scorelines=[],
            prob_btts_yes=50.0,
            prob_btts_no=50.0,
            confidence=90.0,
        )
    )
    db_session.flush()


def test_a_csv_row_completes_the_api_fixture_instead_of_duplicating_it(db_session):
    fixture = _api_fixture(db_session, datetime(2026, 9, 28, 18, 30))
    _predict(db_session, fixture)

    inserted, _, _, api_completed = load_matches(db_session, _frame(_row()))

    assert inserted == []
    assert api_completed == 1
    assert db_session.query(Match).count() == 1
    db_session.refresh(fixture)
    assert fixture.status == "completed"
    assert (fixture.home_score, fixture.away_score) == (2, 1)
    # Its own id and kick-off survive, and the prediction is still attached.
    assert fixture.external_id == "apif-12345"
    assert fixture.match_date == datetime(2026, 9, 28, 18, 30)
    assert db_session.query(Prediction).filter_by(match_id=fixture.id).count() == 1


def test_stats_are_filled_but_never_overwrite_what_the_api_already_recorded(db_session):
    fixture = _api_fixture(db_session, datetime(2026, 9, 28, 18, 30))
    fixture.home_corners = 11  # recorded by the API's own statistics fetch
    db_session.flush()

    load_matches(db_session, _frame(_row()))

    db_session.refresh(fixture)
    assert fixture.home_corners == 11
    assert fixture.home_shots == 14  # was empty, so filled


def test_a_late_kickoff_on_the_adjacent_day_is_still_the_same_fixture(db_session):
    _api_fixture(db_session, datetime(2026, 9, 29, 0, 30))  # UTC; the CSV says the 28th

    inserted, _, _, api_completed = load_matches(db_session, _frame(_row()))

    assert inserted == []
    assert api_completed == 1


def test_a_fixture_days_apart_is_a_different_match(db_session):
    _api_fixture(db_session, datetime(2026, 10, 12, 18, 30))  # the return leg, weeks on

    inserted, _, _, api_completed = load_matches(db_session, _frame(_row()))

    assert len(inserted) == 1
    assert api_completed == 0
    assert db_session.query(Match).count() == 2


def test_the_same_teams_in_another_competition_do_not_collide(db_session):
    _api_fixture(db_session, datetime(2026, 9, 28, 18, 30), competition="Spanish Copa del Rey")

    inserted, _, _, api_completed = load_matches(db_session, _frame(_row()))

    assert len(inserted) == 1
    assert api_completed == 0


def test_an_already_completed_api_fixture_is_left_alone(db_session):
    fixture = _api_fixture(db_session, datetime(2026, 9, 28, 18, 30), status="completed")
    fixture.home_score, fixture.away_score = 3, 3  # what the API recorded
    db_session.flush()

    inserted, _, _, api_completed = load_matches(db_session, _frame(_row()))

    db_session.refresh(fixture)
    assert inserted == []
    # The score the API recorded stands; only its empty stats are filled.
    assert (fixture.home_score, fixture.away_score) == (3, 3)
    assert fixture.home_shots == 14
    assert api_completed == 1
    assert db_session.query(Match).count() == 1


def test_an_ordinary_new_row_is_still_inserted(db_session):
    inserted, _, _, api_completed = load_matches(db_session, _frame(_row()))

    assert len(inserted) == 1
    assert api_completed == 0
    assert inserted[0].status == "completed"


def test_reloading_the_same_file_is_idempotent(db_session):
    frame = _frame(_row())
    load_matches(db_session, frame)
    inserted, _, _, _ = load_matches(db_session, frame)

    assert inserted == []
    assert db_session.query(Match).count() == 1
