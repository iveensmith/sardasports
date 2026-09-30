"""Season-average stats for the match page's Statistics tab.

Goals themselves are already covered by `compute_team_form`; these tests
cover the rest — shots, corners, cards, and the three fields only
`fetch_match_stats.py` can fill (possession, offsides, fouls) — with a
focus on the two ways this would go wrong quietly: mixing seasons together,
and treating a stat a competition never recorded as a zero.
"""

from __future__ import annotations

from datetime import datetime

from app.services.team_service import compute_season_stat_averages


def _match(
    home_team,
    away_team,
    season,
    home_shots=None,
    away_shots=None,
    home_corners=None,
    away_corners=None,
    home_cards=None,
    away_cards=None,
    home_possession=None,
    away_possession=None,
    match_date=None,
):
    return {
        "match_date": match_date or datetime(2026, 1, 1),
        "season": season,
        "home_team": home_team,
        "away_team": away_team,
        "home_shots": home_shots,
        "away_shots": away_shots,
        "home_shots_on_target": None,
        "away_shots_on_target": None,
        "home_corners": home_corners,
        "away_corners": away_corners,
        "home_cards": home_cards,
        "away_cards": away_cards,
        "home_possession": home_possession,
        "away_possession": away_possession,
        "home_offsides": None,
        "away_offsides": None,
        "home_fouls": None,
        "away_fouls": None,
    }


def test_no_history_returns_none():
    assert compute_season_stat_averages([], "Arsenal") is None


def test_averages_are_computed_regardless_of_home_away_side():
    matches = [
        _match("Arsenal", "Chelsea", "2025-2026", home_shots=10, away_shots=8),
        _match("Everton", "Arsenal", "2025-2026", home_shots=6, away_shots=14),
    ]
    result = compute_season_stat_averages(matches, "Arsenal")
    # Arsenal's own shots: 10 (home) and 14 (away) -> average 12.
    assert result["shots"]["value"] == 12.0
    assert result["shots"]["sample_size"] == 2


def test_only_the_current_season_counts():
    """`matches` is sorted ascending by date — the most recent match's
    season is "current"; anything from an earlier season is excluded, not
    blended in."""
    matches = [
        _match(
            "Arsenal",
            "Chelsea",
            "2024-2025",
            home_shots=20,
            match_date=datetime(2025, 1, 1),
        ),
        _match(
            "Arsenal",
            "Everton",
            "2025-2026",
            home_shots=10,
            match_date=datetime(2026, 1, 1),
        ),
    ]
    result = compute_season_stat_averages(matches, "Arsenal")
    assert result["season"] == "2025-2026"
    assert result["matches_played"] == 1
    assert result["shots"]["value"] == 10.0
    assert result["shots"]["sample_size"] == 1


def test_a_stat_the_competition_never_recorded_is_none_not_zero():
    """Possession/offsides/fouls only exist going forward from
    fetch_match_stats.py — a team with a full season of goals can still have
    a genuine sample size of zero for these."""
    matches = [_match("Arsenal", "Chelsea", "2025-2026", home_shots=10)]
    result = compute_season_stat_averages(matches, "Arsenal")
    assert result["possession"]["value"] is None
    assert result["possession"]["sample_size"] == 0
    # But shots, which *was* recorded, is real.
    assert result["shots"]["value"] == 10.0


def test_a_match_missing_the_stat_is_skipped_not_zero_filled():
    """One match recorded corners, one didn't — the average is over the one
    that did, not diluted by treating the gap as a 0."""
    matches = [
        _match("Arsenal", "Chelsea", "2025-2026", home_corners=8),
        _match("Arsenal", "Everton", "2025-2026", home_corners=None),
    ]
    result = compute_season_stat_averages(matches, "Arsenal")
    assert result["corners"]["value"] == 8.0
    assert result["corners"]["sample_size"] == 1


def test_cards_field_is_the_pre_summed_yellow_plus_red():
    """`home_cards`/`away_cards` arrive pre-combined (see
    `get_team_matches_as_dicts`'s `_sum_or_none`) — this just averages
    whatever it's given."""
    matches = [
        _match("Arsenal", "Chelsea", "2025-2026", home_cards=3),
        _match("Arsenal", "Everton", "2025-2026", home_cards=5),
    ]
    result = compute_season_stat_averages(matches, "Arsenal")
    assert result["cards"]["value"] == 4.0
