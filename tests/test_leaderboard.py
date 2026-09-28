"""The model leaderboard's ranking rules.

Two things here are easy to get quietly wrong and would mislead rather than
error: treating a missing baseline as a zero edge, and letting a
small-sample model top the board on noise. Both are pinned.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.api.routes_leaderboard import (
    PROVISIONAL_SAMPLE_THRESHOLD,
    _baseline,
    _row,
    model_leaderboard,
)
from app.models import ModelVersion
from ml.training.common import majority_class_base_rate


def _version(name, accuracy, samples, baseline_key=None, baseline=None, log_loss=0.5):
    metrics = {
        "accuracy": accuracy,
        "log_loss": log_loss,
        "num_test_samples": samples,
    }
    if baseline_key:
        metrics[baseline_key] = baseline
    return ModelVersion(
        model_name=name,
        version="v1",
        artifact_path=f"{name}.txt",
        metrics=metrics,
        is_active=True,
        trained_at=datetime(2026, 9, 28, 12, 0, 0),
    )


# --- the baseline helper the trainers now share --------------------------


def test_majority_class_base_rate_is_the_largest_class_share():
    assert majority_class_base_rate([1, 1, 1, 0]) == pytest.approx(0.75)
    assert majority_class_base_rate([0, 0, 1, 1]) == pytest.approx(0.5)
    # Three classes, as the match-result model has.
    assert majority_class_base_rate([0, 1, 2, 2, 2]) == pytest.approx(0.6)


def test_majority_class_base_rate_handles_an_empty_set():
    assert majority_class_base_rate([]) == 0.0


# --- row derivation -------------------------------------------------------


def test_edge_is_accuracy_minus_baseline_in_points():
    row = _row(
        _version("lightgbm_tennis_winner", 0.6471, 13734, "elo_baseline_accuracy", 0.6428),
        None,
    )
    assert row["accuracy"] == pytest.approx(64.71)
    assert row["baseline"] == pytest.approx(64.28)
    assert row["edge"] == pytest.approx(0.43, abs=0.01)
    assert row["baseline_kind"] == "Always pick the higher rating"


def test_a_missing_baseline_gives_a_null_edge_not_a_zero():
    """Zero would read as "no edge measured to be nil", which is a claim.

    No baseline means we cannot say how much of the accuracy is skill, and
    that is different from saying the skill is none.
    """
    row = _row(_version("gbm_btts", 0.5491, 12873), None)
    assert row["accuracy"] == pytest.approx(54.91)
    assert row["baseline"] is None
    assert row["edge"] is None


def test_small_samples_are_flagged_as_provisional():
    small = _row(_version("lightgbm_basketball_winner", 0.6489, 826), None)
    large = _row(_version("lightgbm_tennis_winner", 0.6471, 13734), None)
    assert small["provisional"] is True
    assert large["provisional"] is False
    assert PROVISIONAL_SAMPLE_THRESHOLD == 1000


def test_trend_is_absent_when_there_is_no_earlier_version():
    """A first-ever model has no trend, which is not the same as flat."""
    assert _row(_version("gbm_btts", 0.55, 100), None)["trend"] is None


def test_trend_is_the_change_since_the_previous_version():
    row = _row(
        _version("gbm_btts", 0.5600, 12873),
        _version("gbm_btts", 0.5400, 12873),
    )
    assert row["trend"] == pytest.approx(2.0, abs=0.01)


def test_baseline_preference_order_is_stable():
    """A model recording several baselines reports the most specific one."""
    metrics = {
        "elo_baseline_accuracy": 0.64,
        "majority_class_base_rate": 0.55,
    }
    value, kind = _baseline(metrics)
    assert value == pytest.approx(64.0)
    assert kind == "Always pick the higher rating"


# --- ranking --------------------------------------------------------------


def test_provisional_models_rank_behind_real_samples(db_session):
    """A few hundred matches can top a board on noise alone.

    The provisional model here has the larger edge and must still sort
    second, so the headline of the board is never a small-sample fluke.
    """
    db_session.add_all(
        [
            _version(
                "lightgbm_basketball_winner", 0.70, 400, "home_win_base_rate", 0.50
            ),  # edge 20, tiny sample
            _version(
                "lightgbm_tennis_winner", 0.60, 13734, "elo_baseline_accuracy", 0.55
            ),  # edge 5, real sample
        ]
    )
    db_session.commit()

    result = model_leaderboard(sport=None, sort="edge", db=db_session)
    ranked = [m["label"] for m in result["models"]]
    assert ranked[0] == "Tennis winner"
    assert ranked[1] == "NBA winner"
    assert result["models"][1]["provisional"] is True


def test_models_without_a_baseline_sort_last(db_session):
    db_session.add_all(
        [
            _version("gbm_btts", 0.90, 12873),  # huge accuracy, no baseline
            _version("lightgbm_tennis_winner", 0.60, 13734, "elo_baseline_accuracy", 0.55),
        ]
    )
    db_session.commit()

    result = model_leaderboard(sport=None, sort="edge", db=db_session)
    assert result["models"][0]["label"] == "Tennis winner"
    assert result["models"][-1]["label"] == "Both teams to score"
    assert result["models"][-1]["edge"] is None


def test_log_loss_sorts_ascending_because_lower_is_better(db_session):
    db_session.add_all(
        [
            _version("gbm_btts", 0.55, 12873, log_loss=0.9),
            _version("lightgbm_tennis_winner", 0.55, 13734, log_loss=0.4),
        ]
    )
    db_session.commit()

    result = model_leaderboard(sport=None, sort="log_loss", db=db_session)
    assert result["models"][0]["log_loss"] == pytest.approx(0.4)


def test_sport_filter_narrows_the_board(db_session):
    db_session.add_all(
        [
            _version("gbm_btts", 0.55, 12873),
            _version("lightgbm_tennis_winner", 0.60, 13734),
        ]
    )
    db_session.commit()

    result = model_leaderboard(sport="tennis", sort="edge", db=db_session)
    assert [m["sport"] for m in result["models"]] == ["tennis"]
