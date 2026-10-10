"""Calibrating the corner and card probabilities.

The corner and card lines ran about five points too confident when graded against what
happened. A fitted curve per line pulls them back; these tests pin that the curve does what
it says, that it is only registered when it helps on matches it was not fitted on, and that
a prediction picks it up.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.models import ModelVersion
from app.services.count_calibration import calibrate_payload
from ml.training import calibrate_count_markets as cal


def test_a_flat_curve_changes_nothing_and_a_shallow_one_pulls_towards_the_middle():
    assert cal.apply_curve(0.7, 1.0, 0.0) == pytest.approx(0.7)
    assert 0.5 < cal.apply_curve(0.7, 0.5, 0.0) < 0.7
    assert 0.3 < cal.apply_curve(0.3, 0.5, 0.0) < 0.5
    assert cal.apply_curve(0.5, 0.5, 0.0) == pytest.approx(0.5)


def _replay(path, market, line, overconfident=True, n=3000, seed=1):
    """A replay file whose raw probabilities are too confident by construction."""
    rng = np.random.default_rng(seed)
    raw = rng.uniform(0.3, 0.85, n)
    truth = 0.5 + 0.45 * (raw - 0.5) if overconfident else raw
    outcome = (rng.uniform(size=n) < truth).astype(int)
    frame = pd.DataFrame(
        {
            "market": market,
            "line": line,
            "competition": "L",
            "date": pd.date_range("2025-01-01", periods=n, freq="h").astype(str),
            "p": raw,
            "y": outcome,
            "model_used": 1,
        }
    )
    frame.to_csv(path, index=False)


def _registered(db_session):
    return {
        v.model_name: v.metrics
        for v in db_session.query(ModelVersion).filter(
            ModelVersion.model_name.like("calibration_%")
        )
    }


def test_an_overconfident_line_gets_a_shallow_curve_that_is_registered(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(cal, "OUT_DIR", tmp_path)
    _replay(tmp_path / "replay_0_of_1.csv", "corners", 8.5, overconfident=True)

    cal.fit()

    curves = _registered(db_session)
    metrics = curves["calibration_corners_over_8_5"]
    assert 0.2 < metrics["slope"] < 0.8  # the true slope here is about 0.45
    assert metrics["log_loss_after"] < metrics["log_loss_before"]


def test_a_line_that_was_already_calibrated_is_left_alone(db_session, tmp_path, monkeypatch):
    """A curve that does not improve matches it was not fitted on is not registered, so a
    well-calibrated line is never touched."""
    monkeypatch.setattr(cal, "OUT_DIR", tmp_path)
    _replay(tmp_path / "replay_0_of_1.csv", "cards", 3.5, overconfident=False, seed=4)

    cal.fit()

    # Allowed either way by chance on noise, but never a materially different curve.
    metrics = _registered(db_session).get("calibration_cards_over_3_5")
    if metrics is not None:
        assert 0.85 < metrics["slope"] < 1.15


def test_too_few_points_register_nothing(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "OUT_DIR", tmp_path)
    _replay(tmp_path / "replay_0_of_1.csv", "corners", 7.5, n=200)

    cal.fit()

    assert _registered(db_session) == {}


def _register_curve(db_session, market, line, slope, intercept):
    from datetime import UTC, datetime

    db_session.add(
        ModelVersion(
            model_name=cal.model_name(market, line),
            version="v1",
            artifact_path="n/a",
            is_active=True,
            trained_at=datetime.now(UTC),
            metrics={"market": market, "line": line, "slope": slope, "intercept": intercept},
        )
    )
    db_session.commit()


def test_a_payload_picks_up_the_registered_curve_and_leaves_other_lines_alone(db_session):
    _register_curve(db_session, "corners", 8.5, 0.5, 0.0)
    payload = {
        "corners_markets": [
            {"line": 8.5, "prob_over": 70.0, "prob_under": 30.0, "model_used": True},
            {"line": 9.5, "prob_over": 60.0, "prob_under": 40.0, "model_used": True},  # no curve
            {"line": 7.5, "prob_over": None, "prob_under": None, "model_used": False},
        ],
        "cards_markets": [{"line": 3.5, "prob_over": 70.0, "prob_under": 30.0}],
    }
    original = payload["corners_markets"][0]

    calibrate_payload(payload)

    pulled, untouched, unavailable = payload["corners_markets"]
    assert 50.0 < pulled["prob_over"] < 70.0
    assert pulled["prob_over"] + pulled["prob_under"] == pytest.approx(100.0, abs=0.11)
    assert untouched["prob_over"] == 60.0
    assert unavailable["prob_over"] is None
    assert payload["cards_markets"][0]["prob_over"] == 70.0  # cards were already calibrated
    assert original["prob_over"] == 70.0  # the stored entry is never edited in place


def test_a_stored_prediction_is_calibrated_on_the_way_out_not_in(db_session):
    """The row keeps the number the engine first produced; the reader sees the calibrated one.
    Applying the curve in both places would correct twice."""
    from datetime import datetime

    from app.models import Match, Prediction, Team
    from app.services.stored_predictions import payload_from_stored

    _register_curve(db_session, "corners", 8.5, 0.5, 0.0)
    home = Team(name="H", sport="football", league="L")
    away = Team(name="A", sport="football", league="L")
    db_session.add_all([home, away])
    db_session.flush()
    match = Match(
        sport="football", competition="L", season="2026", match_date=datetime(2026, 1, 1),
        home_team_id=home.id, away_team_id=away.id, status="scheduled",
    )  # fmt: skip
    db_session.add(match)
    db_session.flush()
    row = Prediction(
        match_id=match.id, prob_home=0.4, prob_draw=0.3, prob_away=0.3, prob_btts_yes=0.5,
        prob_btts_no=0.5, confidence=5.0, confidence_label="Medium",
        expected_goals_home=1.2, expected_goals_away=1.0,
        corners_markets=[{"line": 8.5, "prob_over": 70.0, "prob_under": 30.0}],
    )  # fmt: skip
    db_session.add(row)
    db_session.commit()

    served = payload_from_stored(row)

    assert 50.0 < served["corners_markets"][0]["prob_over"] < 70.0
    assert row.corners_markets[0]["prob_over"] == 70.0
