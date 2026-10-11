"""Calibrating the home / draw / away probabilities.

Replayed out of sample, the blend claimed home wins about two points too often and draws about
two points too rarely in every period. One multinomial correction fixes that; these tests pin
that it does what it says, that it is only registered when it helps on matches it was not
fitted on, and that readers get it without a stored row being rewritten.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from app.models import ModelVersion
from app.services.count_calibration import calibrate_payload
from ml.training import calibrate_match_result as cal


def test_the_identity_correction_changes_nothing():
    home, draw, away = cal.apply_result_calibration(0.5, 0.25, 0.25, 1.0, 0.0, 0.0)
    assert (home, draw, away) == pytest.approx((0.5, 0.25, 0.25))


def test_a_negative_home_offset_moves_probability_off_the_home_side_and_onto_the_rest():
    home, draw, away = cal.apply_result_calibration(0.5, 0.25, 0.25, 1.0, -0.2, 0.2)
    assert home < 0.5 and draw > 0.25 and away > 0.0
    assert home + draw + away == pytest.approx(1.0)


def _replay(path, n=6000, seed=3, biased=True):
    """A replay whose blend overstates the home side and understates the draw, by construction."""
    rng = np.random.default_rng(seed)
    true = rng.dirichlet([5, 3, 3], n)
    if biased:
        claimed = true * np.array([1.12, 0.85, 1.0])
        claimed /= claimed.sum(axis=1, keepdims=True)
    else:
        claimed = true
    outcome = np.array([rng.choice(3, p=row) for row in true])
    pd.DataFrame(
        {
            "match_id": range(n),
            "competition": "L",
            "date": pd.date_range("2025-01-01", periods=n, freq="h").astype(str),
            "outcome": outcome,
            "blend_h": claimed[:, 0],
            "blend_d": claimed[:, 1],
            "blend_a": claimed[:, 2],
        }
    ).to_csv(path, index=False)


def _registered(db_session):
    return (
        db_session.query(ModelVersion)
        .filter(ModelVersion.model_name == cal.MODEL_NAME, ModelVersion.is_active.is_(True))
        .first()
    )


def test_a_biased_blend_gets_a_correction_that_is_registered(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "OUT_DIR", tmp_path)
    _replay(tmp_path / "result_replay_0_of_1.csv")

    cal.fit()

    metrics = _registered(db_session).metrics
    assert metrics["home_offset"] < 0 < metrics["draw_offset"]
    assert metrics["log_loss_after"] < metrics["log_loss_before"]


def test_an_unbiased_blend_is_left_alone(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "OUT_DIR", tmp_path)
    _replay(tmp_path / "result_replay_0_of_1.csv", biased=False, seed=8)

    cal.fit()

    assert _registered(db_session) is None


def test_too_few_matches_register_nothing(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "OUT_DIR", tmp_path)
    _replay(tmp_path / "result_replay_0_of_1.csv", n=300)

    with pytest.raises(SystemExit):
        cal.fit()

    assert _registered(db_session) is None


def _register(db_session, scale=1.0, home_offset=-0.2, draw_offset=0.2):
    db_session.add(
        ModelVersion(
            model_name=cal.MODEL_NAME,
            version="v1",
            artifact_path="n/a",
            is_active=True,
            trained_at=datetime.now(UTC),
            metrics={
                "market": "match_result",
                "scale": scale,
                "home_offset": home_offset,
                "draw_offset": draw_offset,
            },
        )
    )
    db_session.commit()


def test_a_payload_picks_up_the_registered_correction(db_session):
    _register(db_session)
    payload = {"home_win": 50.0, "draw": 25.0, "away_win": 25.0}

    calibrate_payload(payload)

    assert payload["home_win"] < 50.0
    assert payload["draw"] > 25.0
    assert payload["home_win"] + payload["draw"] + payload["away_win"] == pytest.approx(100.0)


def test_a_payload_without_a_registered_correction_is_untouched(db_session):
    payload = {"home_win": 50.0, "draw": 25.0, "away_win": 25.0}

    calibrate_payload(payload)

    assert payload == {"home_win": 50.0, "draw": 25.0, "away_win": 25.0}


def test_a_payload_with_missing_result_figures_does_not_crash(db_session):
    _register(db_session)
    payload = {"home_win": None, "draw": None, "away_win": None}

    calibrate_payload(payload)

    assert payload["home_win"] is None


def test_a_correction_can_be_cleared_and_set_by_hand(db_session):
    _register(db_session)
    assert cal.clear() == 1
    assert _registered(db_session) is None

    cal.set_values(1.05, -0.07, 0.08)
    metrics = _registered(db_session).metrics

    assert (metrics["scale"], metrics["home_offset"], metrics["draw_offset"]) == (1.05, -0.07, 0.08)
    payload = {"home_win": 50.0, "draw": 25.0, "away_win": 25.0}
    calibrate_payload(payload)
    assert payload["home_win"] < 50.0  # and the reader sees it straight away (cache cleared)
