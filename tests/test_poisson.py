"""Tests for ml.poisson.model.PoissonModel."""

from __future__ import annotations

import pytest

from ml.poisson.model import PoissonModel


def _synthetic_matches() -> list[dict]:
    """A small, deterministic synthetic league where "Strong" clearly outscores "Weak"."""
    matches = []
    pairs = [
        ("Strong", "Weak"),
        ("Weak", "Strong"),
        ("Strong", "Mid"),
        ("Mid", "Strong"),
        ("Weak", "Mid"),
        ("Mid", "Weak"),
    ]
    scores = [(3, 0), (0, 2), (2, 1), (1, 1), (0, 1), (1, 2)]
    for _ in range(6):  # repeat the fixture list a few times for a stable fit
        for (home, away), (hg, ag) in zip(pairs, scores, strict=True):
            matches.append(
                {"home_team": home, "away_team": away, "home_score": hg, "away_score": ag}
            )
    return matches


@pytest.fixture
def fitted_model() -> PoissonModel:
    return PoissonModel().fit(_synthetic_matches())


def test_fit_requires_matches():
    with pytest.raises(ValueError):
        PoissonModel().fit([])


def test_stronger_team_has_higher_expected_goals(fitted_model):
    home_xg, away_xg = fitted_model.expected_goals("Strong", "Weak")
    assert home_xg > away_xg


def test_scoreline_matrix_sums_to_one(fitted_model):
    matrix = fitted_model.scoreline_matrix("Strong", "Weak")
    assert matrix.sum() == pytest.approx(1.0, abs=1e-6)


def test_result_probabilities_sum_to_one(fitted_model):
    home, draw, away = fitted_model.result_probabilities("Strong", "Weak")
    assert home + draw + away == pytest.approx(1.0, abs=1e-6)
    assert home > away  # Strong at home vs Weak should be favored


def test_top_scorelines_returns_requested_count(fitted_model):
    top = fitted_model.top_scorelines("Strong", "Weak", n=5)
    assert len(top) == 5
    assert all("score" in row and "probability" in row for row in top)
    # Sorted descending by probability.
    probs = [row["probability"] for row in top]
    assert probs == sorted(probs, reverse=True)


def test_over_under_probabilities_sum_to_one(fitted_model):
    over, under = fitted_model.prob_over_under("Strong", "Weak", line=2.5)
    assert over + under == pytest.approx(1.0, abs=1e-6)


def test_btts_probabilities_sum_to_one(fitted_model):
    yes, no = fitted_model.prob_btts("Strong", "Weak")
    assert yes + no == pytest.approx(1.0, abs=1e-6)


def test_unknown_team_falls_back_to_neutral_strength(fitted_model):
    # Should not raise, and should produce a valid probability distribution
    # even for a team never seen during fit().
    home, draw, away = fitted_model.result_probabilities("Strong", "NeverSeenTeam")
    assert home + draw + away == pytest.approx(1.0, abs=1e-6)
