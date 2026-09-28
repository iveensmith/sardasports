"""Tests for ml.monitoring.value_detection."""

from __future__ import annotations

import pytest

from ml.monitoring.value_detection import compute_value_edges, decimal_odds_to_implied_probabilities


def test_implied_probabilities_sum_to_one():
    home, draw, away = decimal_odds_to_implied_probabilities(2.0, 3.5, 4.0)
    assert home + draw + away == pytest.approx(1.0)


def test_implied_probabilities_removes_overround():
    # Raw 1/odds sums to > 1.0 (the bookmaker's margin); the adjusted
    # probabilities must sum to exactly 1.0.
    raw_sum = 1 / 2.0 + 1 / 3.5 + 1 / 4.0
    assert raw_sum > 1.0
    home, draw, away = decimal_odds_to_implied_probabilities(2.0, 3.5, 4.0)
    assert (home + draw + away) < raw_sum


def test_lower_odds_means_higher_implied_probability():
    home, _, away = decimal_odds_to_implied_probabilities(1.5, 4.0, 6.0)
    assert home > away


def test_compute_value_edges_sorted_by_absolute_edge_descending():
    edges = compute_value_edges(
        model_home=70.0,
        model_draw=20.0,
        model_away=10.0,
        odds_home=2.0,
        odds_draw=3.5,
        odds_away=4.0,
    )
    assert len(edges) == 3
    abs_edges = [abs(e.edge) for e in edges]
    assert abs_edges == sorted(abs_edges, reverse=True)
    assert {e.outcome for e in edges} == {"home_win", "draw", "away_win"}


def test_compute_value_edges_positive_edge_when_model_more_confident():
    # Model gives 70% to home win; market (odds 2.5 -> ~40% raw) implies less.
    edges = compute_value_edges(
        model_home=70.0,
        model_draw=15.0,
        model_away=15.0,
        odds_home=2.5,
        odds_draw=3.4,
        odds_away=3.0,
    )
    home_edge = next(e for e in edges if e.outcome == "home_win")
    assert home_edge.edge > 0  # model is more bullish on home than the market
