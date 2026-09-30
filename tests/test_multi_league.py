"""Tests for multi-league support: competition one-hot features and
Poisson fitting scoped to the target match's own competition.

These exist because blending several leagues into one dataset without
either fix would be a real correctness regression, not just a missing
feature: the Poisson model's league-average goal rate would silently blend
very different scoring environments (e.g. Bundesliga vs. Serie A) into one
wrong number for every league, and the ML models would have no way to tell
which league a match belongs to at all.
"""

from __future__ import annotations

from datetime import datetime

from app.utils.config import get_settings
from ml.prediction.predict import predict_match
from ml.training.common import (
    COMPETITION_COLUMNS,
    FEATURE_COLUMNS,
    KNOWN_COMPETITIONS,
    build_feature_frame,
    one_hot_competition,
)


def test_one_hot_competition_sets_exactly_one_column():
    encoding = one_hot_competition("English Premier League")
    assert encoding["competition_english_premier_league"] == 1.0
    assert sum(encoding.values()) == 1.0
    assert len(encoding) == len(KNOWN_COMPETITIONS)


def test_one_hot_competition_unknown_league_is_all_zero():
    encoding = one_hot_competition("Uruguayan Primera Division")  # not in KNOWN_COMPETITIONS
    assert sum(encoding.values()) == 0.0
    assert len(encoding) == len(KNOWN_COMPETITIONS)


def test_competition_columns_are_part_of_feature_columns():
    assert set(COMPETITION_COLUMNS).issubset(set(FEATURE_COLUMNS))


def _matches(competition: str, home_goals_pattern: list[tuple[int, int]]) -> list[dict]:
    matches = []
    for i, (hg, ag) in enumerate(home_goals_pattern):
        matches.append(
            {
                "home_team": f"{competition[:3]}Home{i}",
                "away_team": f"{competition[:3]}Away{i}",
                "home_score": hg,
                "away_score": ag,
                "match_date": datetime(2024, 1, i + 1),
                "competition": competition,
            }
        )
    return matches


def test_build_feature_frame_sets_correct_competition_flag():
    matches = _matches("German Bundesliga", [(2, 1), (3, 0), (1, 1)])
    settings = get_settings()
    frame = build_feature_frame(matches, settings)

    assert (frame["competition_german_bundesliga"] == 1.0).all()
    assert (frame["competition_english_premier_league"] == 0.0).all()


def test_poisson_fit_is_scoped_to_the_target_competition():
    """The core regression test: a low-scoring league's history must not
    drag down a high-scoring league's expected goals, and vice versa."""
    # A deliberately extreme contrast: Bundesliga-stand-in always 4-3 (high
    # scoring), Serie-A-stand-in always 0-0 (low scoring). Same two "real"
    # teams appear in both, with home/away history built up in each league.
    high_scoring = [
        {
            "home_team": "TeamA",
            "away_team": "TeamB",
            "home_score": 4,
            "away_score": 3,
            "match_date": datetime(2024, 1, d),
            "competition": "High League",
        }
        for d in range(1, 11)
    ]
    low_scoring = [
        {
            "home_team": "TeamA",
            "away_team": "TeamB",
            "home_score": 0,
            "away_score": 0,
            "match_date": datetime(2024, 1, d),
            "competition": "Low League",
        }
        for d in range(1, 11)
    ]
    combined_history = high_scoring + low_scoring

    result_scoped_high = predict_match(
        home_team="TeamA",
        away_team="TeamB",
        match_date=datetime(2024, 2, 1),
        history=combined_history,
        elo_home=1500,
        elo_away=1500,
        elo_k_factor=20,
        elo_home_advantage=60,
        competition="High League",
    )
    result_scoped_low = predict_match(
        home_team="TeamA",
        away_team="TeamB",
        match_date=datetime(2024, 2, 1),
        history=combined_history,
        elo_home=1500,
        elo_away=1500,
        elo_k_factor=20,
        elo_home_advantage=60,
        competition="Low League",
    )

    # Scoped correctly: the high-scoring league's prediction should have
    # much higher expected goals than the low-scoring league's, even though
    # both draw from the exact same combined history and same two teams.
    assert result_scoped_high.expected_goals_home > result_scoped_low.expected_goals_home + 1.0
    assert result_scoped_high.expected_goals_away > result_scoped_low.expected_goals_away + 1.0


def test_poisson_fit_without_competition_blends_leagues_unscoped():
    """Confirms the *old* (competition=None) behavior still works as a
    fallback for callers that don't have a competition — it blends
    everything together, which is exactly the behavior competition-scoping
    exists to avoid when a competition IS known."""
    high_scoring = [
        {
            "home_team": "TeamA",
            "away_team": "TeamB",
            "home_score": 4,
            "away_score": 3,
            "match_date": datetime(2024, 1, d),
            "competition": "High League",
        }
        for d in range(1, 11)
    ]
    result = predict_match(
        home_team="TeamA",
        away_team="TeamB",
        match_date=datetime(2024, 2, 1),
        history=high_scoring,
        elo_home=1500,
        elo_away=1500,
        elo_k_factor=20,
        elo_home_advantage=60,
        competition=None,
    )
    assert result.expected_goals_home > 0
