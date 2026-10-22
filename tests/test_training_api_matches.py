"""Training sees the enabled API competitions, which live only in the database.

`scripts/fetch_api_competitions.py` writes to the database and never to
`data/processed/matches.csv`, which is what the models train on. Before this,
enabling a competition added its one-hot column and retrained every model
without one of its matches in the training set: the column would have been
all zeros in training, so the model could learn nothing about it.
"""

from __future__ import annotations

import math
from datetime import datetime

import pandas as pd
import pytest

import ml.api_competitions as api_competitions
import ml.training.common as common
from app.models import Match, Team
from ml.api_competitions import BY_ID

UCL = BY_ID[2]


@pytest.fixture(autouse=True)
def _champions_league_is_enabled(monkeypatch):
    """These tests are about what happens to an enabled competition, whichever ones are."""
    monkeypatch.setattr(api_competitions, "ENABLED_IDS", frozenset({2}))


def _match(db_session, competition, kickoff, status="completed", score=(2, 1), suffix="a"):
    home = Team(name=f"Home {suffix}", league="x", sport="football")
    away = Team(name=f"Away {suffix}", league="x", sport="football")
    db_session.add_all([home, away])
    db_session.flush()
    match = Match(
        external_id=f"apif-{suffix}",
        match_date=kickoff,
        competition=competition,
        season="2025-2026",
        home_team_id=home.id,
        away_team_id=away.id,
        status=status,
        home_score=score[0] if status == "completed" else None,
        away_score=score[1] if status == "completed" else None,
        home_corners=6,
        neutral_venue=False,
    )
    db_session.add(match)
    db_session.commit()
    return match


def test_a_played_match_of_an_enabled_competition_is_a_training_row(db_session):
    _match(db_session, UCL.name, datetime(2025, 11, 5, 20, 0), suffix="played")

    rows = common.load_enabled_api_matches()

    assert len(rows) == 1
    row = rows[0]
    assert row["competition"] == UCL.name
    assert (row["home_team"], row["away_team"]) == ("Home played", "Away played")
    assert (row["home_score"], row["away_score"]) == (2, 1)
    # Cut to the date, like the CSV rows it is merged with.
    assert row["match_date"] == pd.Timestamp("2025-11-05")
    assert row["home_corners"] == 6
    # A figure the match never recorded is NaN, as pandas leaves it for the CSV rows.
    assert math.isnan(row["away_corners"]) and math.isnan(row["odds_home_win"])


def test_unplayed_and_other_competitions_are_not_training_rows(db_session):
    _match(db_session, UCL.name, datetime(2026, 11, 5, 20, 0), status="scheduled", suffix="later")
    _match(db_session, "English Premier League", datetime(2025, 11, 5, 15, 0), suffix="epl")

    assert common.load_enabled_api_matches() == []


def test_they_join_the_csv_rows_in_the_training_set(db_session, tmp_path, monkeypatch):
    csv_path = tmp_path / "matches.csv"
    pd.DataFrame(
        [
            {
                "external_id": "csv-1",
                "match_date": "2025-10-01",
                "competition": "English Premier League",
                "season": "2025-2026",
                "neutral_venue": False,
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "home_score": 1,
                "away_score": 1,
            }
        ]
    ).to_csv(csv_path, index=False)
    monkeypatch.setattr(common, "PROCESSED_PATH", csv_path)
    _match(db_session, UCL.name, datetime(2025, 11, 5, 20, 0), suffix="joined")

    matches = common.load_processed_matches(min_matches=1)

    assert {m["competition"] for m in matches} == {"English Premier League", UCL.name}
    assert len(matches) == 2
