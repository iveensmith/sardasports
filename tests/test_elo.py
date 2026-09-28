"""Tests for ml.elo.engine.EloEngine."""

from __future__ import annotations

from datetime import datetime

import pytest

from ml.elo.engine import EloEngine, MatchResult


def test_new_team_gets_initial_rating():
    engine = EloEngine(initial_rating=1500.0)
    assert engine.get_rating("Arsenal") == 1500.0


def test_expected_score_is_symmetric_at_equal_ratings():
    assert EloEngine.expected_score(1500, 1500) == pytest.approx(0.5)


def test_expected_score_favors_higher_rated_team():
    assert EloEngine.expected_score(1700, 1500) > 0.5
    assert EloEngine.expected_score(1500, 1700) < 0.5


def test_winner_rating_increases_and_loser_decreases():
    engine = EloEngine(k_factor=20, home_advantage=0)
    engine.set_rating("Arsenal", 1500)
    engine.set_rating("Chelsea", 1500)

    update = engine.apply_result(
        MatchResult(
            home_team="Arsenal",
            away_team="Chelsea",
            home_score=2,
            away_score=0,
            match_date=datetime(2024, 1, 1),
        )
    )

    assert update.home_rating_after > update.home_rating_before
    assert update.away_rating_after < update.away_rating_before
    # Zero-sum-ish (not exactly, due to the margin-of-victory multiplier being
    # applied identically to both sides, so total movement is symmetric).
    home_delta = update.home_rating_after - update.home_rating_before
    away_delta = update.away_rating_after - update.away_rating_before
    assert home_delta == pytest.approx(-away_delta)


def test_draw_leaves_equal_ratings_unchanged():
    engine = EloEngine(k_factor=20, home_advantage=0)
    engine.set_rating("Arsenal", 1500)
    engine.set_rating("Chelsea", 1500)

    update = engine.apply_result(
        MatchResult(
            home_team="Arsenal",
            away_team="Chelsea",
            home_score=1,
            away_score=1,
            match_date=datetime(2024, 1, 1),
        )
    )
    assert update.home_rating_after == pytest.approx(1500.0)
    assert update.away_rating_after == pytest.approx(1500.0)


def test_bigger_margin_moves_rating_more():
    engine_small = EloEngine(k_factor=20, home_advantage=0)
    engine_small.set_rating("A", 1500)
    engine_small.set_rating("B", 1500)
    small_update = engine_small.apply_result(
        MatchResult(
            home_team="A",
            away_team="B",
            home_score=1,
            away_score=0,
            match_date=datetime(2024, 1, 1),
        )
    )

    engine_big = EloEngine(k_factor=20, home_advantage=0)
    engine_big.set_rating("A", 1500)
    engine_big.set_rating("B", 1500)
    big_update = engine_big.apply_result(
        MatchResult(
            home_team="A",
            away_team="B",
            home_score=4,
            away_score=0,
            match_date=datetime(2024, 1, 1),
        )
    )

    small_delta = small_update.home_rating_after - small_update.home_rating_before
    big_delta = big_update.home_rating_after - big_update.home_rating_before
    assert big_delta > small_delta


def test_home_advantage_boosts_home_win_probability():
    engine = EloEngine(home_advantage=100)
    engine.set_rating("Arsenal", 1500)
    engine.set_rating("Chelsea", 1500)
    home_win, draw, away_win = engine.result_probabilities("Arsenal", "Chelsea")

    assert home_win > away_win
    assert home_win + draw + away_win == pytest.approx(1.0)


def test_replay_applies_matches_in_given_order():
    engine = EloEngine()
    matches = [
        MatchResult("A", "B", 1, 0, datetime(2024, 1, 1)),
        MatchResult("B", "A", 2, 2, datetime(2024, 1, 8)),
    ]
    updates = engine.replay(matches)
    assert len(updates) == 2
    # Second update's "before" ratings must equal the first update's "after" ratings.
    assert updates[1].away_rating_before == pytest.approx(updates[0].home_rating_after)
