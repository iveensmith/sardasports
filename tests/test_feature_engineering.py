"""Tests for ml.feature_engineering.features — correctness and leakage-safety."""

from __future__ import annotations

from datetime import datetime

from ml.feature_engineering.features import (
    build_match_features,
    build_team_history_index,
    compute_corner_form,
    compute_head_to_head,
    compute_rest_days,
    compute_team_form,
    feature_completeness,
)


def _history() -> list[dict]:
    return [
        {
            "home_team": "A",
            "away_team": "B",
            "home_score": 2,
            "away_score": 0,
            "match_date": datetime(2024, 1, 1),
        },
        {
            "home_team": "B",
            "away_team": "A",
            "home_score": 1,
            "away_score": 1,
            "match_date": datetime(2024, 1, 8),
        },
        {
            "home_team": "A",
            "away_team": "C",
            "home_score": 3,
            "away_score": 1,
            "match_date": datetime(2024, 1, 15),
        },
        # "Future" matches relative to the target date used in tests below.
        {
            "home_team": "A",
            "away_team": "B",
            "home_score": 0,
            "away_score": 5,
            "match_date": datetime(2024, 2, 1),
        },
        {
            "home_team": "C",
            "away_team": "A",
            "home_score": 0,
            "away_score": 0,
            "match_date": datetime(2024, 2, 8),
        },
    ]


def test_compute_team_form_only_counts_prior_matches():
    history = _history()
    target_date = datetime(2024, 1, 20)  # strictly after the first 3 matches, before the last 2

    form = compute_team_form("A", history, before_date=target_date)
    assert form.matches_played == 3  # the three A matches before Jan 20 (Jan 1, Jan 8, Jan 15)
    assert form.wins == 2  # 2-0 and 3-1 wins
    assert form.draws == 1  # 1-1 draw
    assert form.losses == 0
    assert form.goals_scored == 2 + 1 + 3
    assert form.goals_conceded == 0 + 1 + 1


def test_feature_leakage_guard_ignores_future_matches():
    """Features computed for a match must be identical whether the history list
    includes only prior matches, or the entire dataset (past + future)."""
    history = _history()
    target_date = datetime(2024, 1, 20)

    prior_only = [m for m in history if m["match_date"] < target_date]

    features_full_dataset = build_match_features("A", "C", target_date, history)
    features_prior_only = build_match_features("A", "C", target_date, prior_only)

    assert features_full_dataset == features_prior_only


def test_compute_rest_days():
    history = _history()
    target_date = datetime(2024, 1, 20)
    rest_days = compute_rest_days("A", history, target_date)
    # Team A's most recent prior match before Jan 20 was Jan 15.
    assert rest_days == 5


def test_compute_rest_days_none_when_no_history():
    assert compute_rest_days("NewTeam", _history(), datetime(2024, 1, 20)) is None


def test_head_to_head_counts_only_meetings_between_the_two_teams():
    history = _history()
    h2h = compute_head_to_head("A", "B", history, before_date=datetime(2024, 3, 1))
    assert h2h["h2h_matches_played"] == 3  # all 3 A-vs-B matches are before Mar 1
    assert h2h["h2h_home_team_wins"] + h2h["h2h_draws"] + h2h["h2h_away_team_wins"] == 3


def test_feature_completeness_full_when_elo_and_history_present():
    features = build_match_features(
        "A", "B", datetime(2024, 1, 20), _history(), elo_home=1500, elo_away=1480
    )
    assert feature_completeness(features) == 1.0


def test_feature_completeness_partial_for_brand_new_teams_with_no_elo():
    features = build_match_features("NewA", "NewB", datetime(2024, 1, 20), [])
    # No history -> rest_days is None for both, and elo_home/elo_away/elo_diff are None.
    assert feature_completeness(features) < 1.0


def test_indexed_history_produces_identical_results_to_flat_list():
    """Correctness check for the performance optimization: a pre-built
    TeamHistoryIndex must give byte-for-byte the same features as the plain
    list it was built from — the index changes *how fast* lookups are, not
    *what* they return."""
    history = _history()
    target_date = datetime(2024, 1, 20)
    index = build_team_history_index(history)

    features_flat_list = build_match_features("A", "C", target_date, history)
    features_indexed = build_match_features("A", "C", target_date, index)

    assert features_flat_list == features_indexed


def test_compute_corner_form_none_when_no_corner_data_recorded():
    """`_history()`'s fixture matches have no `home_corners`/`away_corners`
    keys at all (like MLS/Saudi Pro League matches in the real pipeline) —
    corner form must come back None, not a crash or a silent zero."""
    form = compute_corner_form("A", _history(), before_date=datetime(2024, 1, 20))
    assert form == {"avg_corners_won": None, "avg_corners_conceded": None}


def test_compute_corner_form_averages_only_matches_with_corner_data():
    history = [
        {
            "home_team": "A",
            "away_team": "B",
            "home_score": 1,
            "away_score": 0,
            "home_corners": 6,
            "away_corners": 2,
            "match_date": datetime(2024, 1, 1),
        },
        {
            # No corner data recorded for this one (e.g. a season/league gap)
            # — must be skipped, not treated as 0 corners.
            "home_team": "B",
            "away_team": "A",
            "home_score": 1,
            "away_score": 1,
            "home_corners": None,
            "away_corners": None,
            "match_date": datetime(2024, 1, 8),
        },
        {
            "home_team": "A",
            "away_team": "C",
            "home_score": 2,
            "away_score": 2,
            "home_corners": 4,
            "away_corners": 8,
            "match_date": datetime(2024, 1, 15),
        },
    ]
    form = compute_corner_form("A", history, before_date=datetime(2024, 1, 20))
    # Only the two matches with real corner data count: won (6, 4) -> 5.0,
    # conceded (2, 8) -> 5.0. The Jan 8 match (no corner data) is excluded
    # from both the numerator and the denominator.
    assert form == {"avg_corners_won": 5.0, "avg_corners_conceded": 5.0}


def test_build_match_features_includes_corner_form_keys():
    features = build_match_features("A", "C", datetime(2024, 1, 20), _history())
    assert "home_avg_corners_won" in features
    assert "home_avg_corners_conceded" in features
    assert "away_avg_corners_won" in features
    assert "away_avg_corners_conceded" in features
    # None, matching the no-corner-data fixture history.
    assert features["home_avg_corners_won"] is None


def test_indexed_history_is_also_leakage_safe():
    history = _history()
    target_date = datetime(2024, 1, 20)
    prior_only = [m for m in history if m["match_date"] < target_date]

    index_full = build_team_history_index(history)
    index_prior_only = build_team_history_index(prior_only)

    features_full = build_match_features("A", "C", target_date, index_full)
    features_prior_only = build_match_features("A", "C", target_date, index_prior_only)

    assert features_full == features_prior_only
