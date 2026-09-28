"""Tests for the corners/cards markets: the reused-PoissonModel baseline (one
fit, reused across every offered line), graceful unavailability when a
competition has no corner/card data, and that the new corner-form features
never leak the target match's own outcome into the training input.

These exist because several things could silently go wrong without them:
(1) the Poisson baseline (fit on relabeled corner/card counts instead of
goals) could get the relabeling backwards or blend competitions the way the
pre-multi-league Poisson bug once did for goals, (2) a competition with
zero recorded corners/cards (MLS, Saudi Pro League) must report every line
of the market as unavailable (None) rather than a fabricated number from
zero-filled features, and (3) each line must actually be a distinct
Over/Under calculation (not, say, all lines silently returning the same
number).
"""

from __future__ import annotations

from datetime import datetime

from app.utils.config import get_settings
from ml.prediction.predict import CARDS_LINES, CORNERS_LINES, predict_match
from ml.training.common import FEATURE_COLUMNS, build_feature_frame


def _matches_with_corners(competition: str, pattern: list[tuple[int, int, int, int]]) -> list[dict]:
    """Each pattern entry is (home_score, away_score, home_corners, away_corners)."""
    matches = []
    for i, (hg, ag, hc, ac) in enumerate(pattern):
        matches.append(
            {
                "home_team": "TeamA",
                "away_team": "TeamB",
                "home_score": hg,
                "away_score": ag,
                "home_corners": hc,
                "away_corners": ac,
                "match_date": datetime(2024, 1, i + 1),
                "competition": competition,
            }
        )
    return matches


def _markets_by_line(markets: list[dict]) -> dict[float, dict]:
    return {m["line"]: m for m in markets}


def test_corners_markets_cover_every_offered_line():
    history = _matches_with_corners("Some League", [(1, 1, 10, 8) for _ in range(10)])
    result = predict_match(
        home_team="TeamA",
        away_team="TeamB",
        match_date=datetime(2024, 2, 1),
        history=history,
        elo_home=1500,
        elo_away=1500,
        elo_k_factor=20,
        elo_home_advantage=60,
        competition="Some League",
    )
    lines = [m["line"] for m in result.corners_markets]
    assert lines == CORNERS_LINES


def test_cards_markets_cover_every_offered_line():
    history = [
        {
            "home_team": "TeamA",
            "away_team": "TeamB",
            "home_score": 1,
            "away_score": 1,
            "home_yellow_cards": 2,
            "away_yellow_cards": 1,
            "home_red_cards": 0,
            "away_red_cards": 0,
            "match_date": datetime(2024, 1, i + 1),
            "competition": "Some League",
        }
        for i in range(10)
    ]
    result = predict_match(
        home_team="TeamA",
        away_team="TeamB",
        match_date=datetime(2024, 2, 1),
        history=history,
        elo_home=1500,
        elo_away=1500,
        elo_k_factor=20,
        elo_home_advantage=60,
        competition="Some League",
    )
    lines = [m["line"] for m in result.cards_markets]
    assert lines == CARDS_LINES


def test_corners_poisson_baseline_is_scoped_to_the_target_competition():
    """Mirrors tests/test_multi_league.py's Poisson-scoping regression test,
    but for corners instead of goals: a high-corner league's history must
    not drag down a low-corner league's, and vice versa."""
    high_corners = _matches_with_corners("High Corner League", [(1, 1, 14, 12) for _ in range(10)])
    low_corners = _matches_with_corners("Low Corner League", [(1, 1, 3, 2) for _ in range(10)])
    combined_history = high_corners + low_corners

    result_high = predict_match(
        home_team="TeamA",
        away_team="TeamB",
        match_date=datetime(2024, 2, 1),
        history=combined_history,
        elo_home=1500,
        elo_away=1500,
        elo_k_factor=20,
        elo_home_advantage=60,
        competition="High Corner League",
    )
    result_low = predict_match(
        home_team="TeamA",
        away_team="TeamB",
        match_date=datetime(2024, 2, 1),
        history=combined_history,
        elo_home=1500,
        elo_away=1500,
        elo_k_factor=20,
        elo_home_advantage=60,
        competition="Low Corner League",
    )

    high_9_5 = _markets_by_line(result_high.corners_markets)[9.5]
    low_9_5 = _markets_by_line(result_low.corners_markets)[9.5]
    assert high_9_5["prob_over"] is not None
    assert low_9_5["prob_over"] is not None
    # High-corner league (26 total/match) should be near-certain "over 9.5";
    # low-corner league (5 total/match) should be near-certain "under 9.5".
    assert high_9_5["prob_over"] > low_9_5["prob_over"] + 30


def test_corners_lines_are_genuinely_different_calculations():
    """The three corners lines must not all collapse to the same number —
    each is a real, distinct Over/Under calculation off the same Poisson
    fit, so a higher line should always show a lower (or equal) P(over)."""
    history = _matches_with_corners("Some League", [(1, 1, 6, 5) for _ in range(10)])  # 11 total
    result = predict_match(
        home_team="TeamA",
        away_team="TeamB",
        match_date=datetime(2024, 2, 1),
        history=history,
        elo_home=1500,
        elo_away=1500,
        elo_k_factor=20,
        elo_home_advantage=60,
        competition="Some League",
    )
    by_line = _markets_by_line(result.corners_markets)
    assert by_line[7.5]["prob_over"] >= by_line[8.5]["prob_over"] >= by_line[9.5]["prob_over"]
    # And not literally identical across all three (a real Poisson spread).
    assert by_line[7.5]["prob_over"] > by_line[9.5]["prob_over"]


def test_corners_and_cards_market_unavailable_when_competition_has_no_data():
    """A competition with zero recorded corners/cards (MLS, Saudi Pro
    League, in the real pipeline) must report every line of both markets as
    genuinely unavailable, not silently compute a meaningless number from
    an all-zero-filled feature vector."""
    history = [
        {
            "home_team": "TeamA",
            "away_team": "TeamB",
            "home_score": 1,
            "away_score": 0,
            "match_date": datetime(2024, 1, i + 1),
            "competition": "No Stats League",
            # No home_corners/away_corners/cards keys at all.
        }
        for i in range(5)
    ]

    result = predict_match(
        home_team="TeamA",
        away_team="TeamB",
        match_date=datetime(2024, 2, 1),
        history=history,
        elo_home=1500,
        elo_away=1500,
        elo_k_factor=20,
        elo_home_advantage=60,
        competition="No Stats League",
    )

    assert [m["line"] for m in result.corners_markets] == CORNERS_LINES
    assert all(m["prob_over"] is None and m["prob_under"] is None for m in result.corners_markets)
    assert all(m["model_used"] is False for m in result.corners_markets)
    assert [m["line"] for m in result.cards_markets] == CARDS_LINES
    assert all(m["prob_over"] is None and m["prob_under"] is None for m in result.cards_markets)
    assert all(m["model_used"] is False for m in result.cards_markets)


def test_corners_and_cards_columns_never_leak_into_feature_columns():
    """`total_corners`/`total_cards` (the target match's own actual totals,
    used only to derive the training label) must never appear in
    FEATURE_COLUMNS — that would leak the outcome being predicted into the
    model's input."""
    assert "total_corners" not in FEATURE_COLUMNS
    assert "total_cards" not in FEATURE_COLUMNS
    assert "home_avg_corners_won" in FEATURE_COLUMNS
    assert "away_avg_corners_conceded" in FEATURE_COLUMNS


def test_build_feature_frame_derives_total_corners_and_cards():
    matches = [
        {
            "home_team": "TeamA",
            "away_team": "TeamB",
            "home_score": 2,
            "away_score": 1,
            "home_corners": 6,
            "away_corners": 5,
            "home_yellow_cards": 2,
            "away_yellow_cards": 1,
            "home_red_cards": 0,
            "away_red_cards": 1,
            "match_date": datetime(2024, 1, 1),
            "competition": "Some League",
        },
        {
            # Missing corner/card data entirely for this one.
            "home_team": "TeamB",
            "away_team": "TeamA",
            "home_score": 0,
            "away_score": 0,
            "match_date": datetime(2024, 1, 8),
            "competition": "Some League",
        },
    ]
    settings = get_settings()
    frame = build_feature_frame(matches, settings)

    assert frame.loc[0, "total_corners"] == 11
    assert frame.loc[0, "total_cards"] == 4
    assert frame.loc[1, "total_corners"] is None or frame.isna().loc[1, "total_corners"]
    assert frame.loc[1, "total_cards"] is None or frame.isna().loc[1, "total_cards"]
