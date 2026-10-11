"""The Dixon-Coles goal model: a drop-in for `PoissonModel` with three stated differences."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import numpy as np
import pytest

from ml.poisson.model import DixonColesModel, PoissonModel, _dc_tau

TEAMS = [f"T{i}" for i in range(8)]


def _matches(n=600, seed=3, draw_bias=False):
    rng = random.Random(seed)
    start = datetime(2024, 1, 1)
    rows = []
    for k in range(n):
        home, away = rng.sample(TEAMS, 2)
        scores = [0, 0, 1, 1, 1, 2, 2, 3]
        h, a = rng.choice(scores), rng.choice([0, 0, 1, 1, 2])
        if draw_bias and rng.random() < 0.15:
            h = a = rng.choice([0, 1])
        rows.append(
            {
                "home_team": home,
                "away_team": away,
                "home_score": h,
                "away_score": a,
                "match_date": start + timedelta(days=k // 3),
            }
        )
    return rows


def test_with_nothing_extra_it_is_exactly_the_parent_model_without_double_counted_home_advantage():
    rows = _matches()
    parent = PoissonModel(home_advantage=1.0).fit(rows)
    child = DixonColesModel(fit_rho=False).fit(rows)

    for team in TEAMS:
        assert child.team_strength[team].attack == pytest.approx(parent.team_strength[team].attack)
        assert child.team_strength[team].defense == pytest.approx(
            parent.team_strength[team].defense
        )
    assert child.result_probabilities("T0", "T1") == pytest.approx(
        parent.result_probabilities("T0", "T1")
    )


def test_the_parent_default_is_unchanged_so_corner_and_card_models_are_untouched():
    """Corners, cards and half-time goals still use `PoissonModel`, and their registered
    calibrations were fitted to its behaviour: its default must not move."""
    assert PoissonModel().home_advantage == 1.15
    assert DixonColesModel().home_advantage == 1.0


def test_the_scoreline_matrix_is_a_distribution_whatever_rho_is():
    rows = _matches(draw_bias=True)
    for rho in (-0.2, -0.05, 0.0, 0.1):
        model = DixonColesModel(fit_rho=False, rho=rho).fit(rows)
        model.rho = rho
        matrix = model.scoreline_matrix("T0", "T1")
        assert float(matrix.sum()) == pytest.approx(1.0)
        assert (matrix >= 0).all()


def test_the_correction_leaves_the_probabilities_it_adjusts_summing_to_one():
    """The four tau factors are chosen so the independent probabilities of the low cells sum to
    what they did before, which is why no renormalisation is needed for the correction."""
    lam, mu, rho = 1.4, 1.1, -0.1
    from math import exp, factorial

    def pmf(k, x):
        return exp(-x) * x**k / factorial(k)

    before = sum(pmf(i, lam) * pmf(j, mu) for i in (0, 1) for j in (0, 1))
    cells = [(i, j) for i in (0, 1) for j in (0, 1)]
    after = sum(pmf(i, lam) * pmf(j, mu) * _dc_tau(i, j, lam, mu, rho) for i, j in cells)
    assert after == pytest.approx(before)


def test_a_negative_rho_moves_probability_onto_the_low_scoring_draws():
    rows = _matches(draw_bias=True)
    plain = DixonColesModel(fit_rho=False).fit(rows)
    shaped = DixonColesModel(fit_rho=False).fit(rows)
    shaped.rho = -0.15

    p, q = plain.scoreline_matrix("T0", "T1"), shaped.scoreline_matrix("T0", "T1")

    assert q[0, 0] > p[0, 0] and q[1, 1] > p[1, 1]
    assert q[1, 0] < p[1, 0] and q[0, 1] < p[0, 1]
    assert q.sum() == pytest.approx(p.sum())


def test_rho_is_estimated_from_the_matches_and_is_negative_when_low_draws_are_over_represented():
    rho = DixonColesModel().fit(_matches(n=2000, draw_bias=True)).rho
    assert -0.5 < rho < 0.0


def test_recent_matches_count_for_more_when_decay_is_on():
    rows = []
    start = datetime(2024, 1, 1)
    # T0 scored a lot long ago and nothing recently; T1 is the opposite.
    for k in range(60):
        old, new = start + timedelta(days=k), start + timedelta(days=400 + k)
        base = {"home_team": "T0", "away_team": "T2"}
        rows.append({**base, "home_score": 3, "away_score": 0, "match_date": old})
        rows.append({**base, "home_score": 0, "away_score": 1, "match_date": new})
    flat = DixonColesModel(fit_rho=False).fit(rows)
    decayed = DixonColesModel(fit_rho=False, decay_per_day=0.01).fit(rows)

    assert decayed.team_strength["T0"].attack < flat.team_strength["T0"].attack


def test_without_dates_decay_is_ignored_rather_than_failing():
    rows = [{k: v for k, v in m.items() if k != "match_date"} for m in _matches(n=100)]
    model = DixonColesModel(decay_per_day=0.01).fit(rows)
    assert np.isfinite(model.result_probabilities("T0", "T1")).all()


def test_an_empty_fit_is_an_error_like_the_parent():
    with pytest.raises(ValueError):
        DixonColesModel().fit([])
