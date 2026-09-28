"""Tests for ml.monitoring.evaluation / calibration / drift."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.models import Match, PredictionHistory, Team, TrainingRun
from ml.monitoring.calibration import build_calibration_report
from ml.monitoring.drift import check_drift, check_feature_drift
from ml.monitoring.evaluation import (
    actual_result_label,
    backfill_actual_results,
    predicted_result_label,
)
from ml.training.common import compute_feature_summary


def test_actual_result_label():
    assert actual_result_label(2, 0) == "home_win"
    assert actual_result_label(0, 2) == "away_win"
    assert actual_result_label(1, 1) == "draw"


def test_predicted_result_label_picks_the_argmax():
    assert predicted_result_label(70, 20, 10) == "home_win"
    assert predicted_result_label(10, 20, 70) == "away_win"
    assert predicted_result_label(20, 60, 20) == "draw"


def _seed_completed_match_with_prediction(
    db_session, home_score: int, away_score: int, prob_home: float
):
    home = Team(name="Arsenal")
    away = Team(name="Chelsea")
    db_session.add_all([home, away])
    db_session.flush()

    match = Match(
        match_date=datetime(2024, 1, 1),
        competition="English Premier League",
        season="2023-2024",
        home_team_id=home.id,
        away_team_id=away.id,
        home_score=home_score,
        away_score=away_score,
        status="completed",
    )
    db_session.add(match)
    db_session.flush()

    history = PredictionHistory(
        match_id=match.id,
        prob_home=prob_home,
        prob_draw=(1 - prob_home) / 2,
        prob_away=(1 - prob_home) / 2,
        expected_goals_home=1.5,
        expected_goals_away=1.0,
        top_scorelines=[],
        prob_btts_yes=0.5,
        prob_btts_no=0.5,
        confidence=70.0,
        confidence_label="Medium",
    )
    db_session.add(history)
    db_session.commit()
    return match, history


def test_backfill_actual_results_fills_in_missing_outcomes(db_session):
    match, history = _seed_completed_match_with_prediction(db_session, 2, 0, prob_home=0.7)
    assert history.actual_home_goals is None

    updated = backfill_actual_results(db_session)
    assert updated == 1

    db_session.refresh(history)
    assert history.actual_home_goals == 2
    assert history.actual_away_goals == 0


def test_backfill_is_idempotent(db_session):
    _seed_completed_match_with_prediction(db_session, 2, 0, prob_home=0.7)
    first = backfill_actual_results(db_session)
    second = backfill_actual_results(db_session)
    assert first == 1
    assert second == 0  # nothing left to backfill


def test_calibration_report_reflects_a_correct_confident_prediction(db_session):
    _seed_completed_match_with_prediction(db_session, 2, 0, prob_home=0.9)
    backfill_actual_results(db_session)

    report = build_calibration_report(db_session)
    assert report.num_predictions == 1
    assert report.overall_accuracy == 100.0
    assert report.brier_score < 0.1  # confident and correct -> low Brier score
    assert len(report.buckets) == 1
    assert report.buckets[0].actual_accuracy == 100.0


def test_calibration_report_empty_when_no_evaluated_predictions(db_session):
    report = build_calibration_report(db_session)
    assert report.num_predictions == 0
    assert report.buckets == []


def test_drift_not_enough_history_with_fewer_than_two_runs(db_session):
    db_session.add(
        TrainingRun(
            model_name="xgboost_match_result",
            status="success",
            metrics={"accuracy": 0.5, "log_loss": 1.0},
            started_at=datetime(2024, 1, 1),
        )
    )
    db_session.commit()

    status = check_drift(db_session, model_name="xgboost_match_result")
    assert status.has_enough_history is False
    assert status.drift_detected is False


def test_drift_detected_on_accuracy_drop(db_session):
    db_session.add_all(
        [
            TrainingRun(
                model_name="xgboost_match_result",
                status="success",
                metrics={"accuracy": 0.55, "log_loss": 1.0},
                started_at=datetime(2024, 1, 1),
            ),
            TrainingRun(
                model_name="xgboost_match_result",
                status="success",
                metrics={"accuracy": 0.40, "log_loss": 1.1},
                started_at=datetime(2024, 2, 1),
            ),
        ]
    )
    db_session.commit()

    status = check_drift(db_session, model_name="xgboost_match_result")
    assert status.has_enough_history is True
    assert status.drift_detected is True
    assert any("Accuracy dropped" in r for r in status.reasons)


def test_no_drift_when_metrics_stable(db_session):
    db_session.add_all(
        [
            TrainingRun(
                model_name="xgboost_match_result",
                status="success",
                metrics={"accuracy": 0.50, "log_loss": 1.05},
                started_at=datetime(2024, 1, 1),
            ),
            TrainingRun(
                model_name="xgboost_match_result",
                status="success",
                metrics={"accuracy": 0.51, "log_loss": 1.04},
                started_at=datetime(2024, 2, 1),
            ),
        ]
    )
    db_session.commit()

    status = check_drift(db_session, model_name="xgboost_match_result")
    assert status.drift_detected is False


def test_compute_feature_summary_returns_mean_and_std():
    df = pd.DataFrame({"elo_diff": [10.0, 20.0, 30.0], "home_rest_days": [5.0, 5.0, 5.0]})
    summary = compute_feature_summary(df, feature_columns=["elo_diff", "home_rest_days"])
    assert summary["elo_diff"]["mean"] == 20.0
    assert summary["home_rest_days"]["mean"] == 5.0
    assert summary["home_rest_days"]["std"] == 0.0  # constant column -> zero spread


def test_compute_feature_summary_skips_all_nan_columns():
    df = pd.DataFrame({"elo_diff": [10.0, 20.0], "missing_feature": [None, None]})
    summary = compute_feature_summary(df, feature_columns=["elo_diff", "missing_feature"])
    assert "elo_diff" in summary
    assert "missing_feature" not in summary


def _training_run(model_name, feature_summary, started_at):
    return TrainingRun(
        model_name=model_name,
        status="success",
        metrics={"accuracy": 0.5, "log_loss": 1.0, "feature_summary": feature_summary},
        started_at=started_at,
    )


def test_feature_drift_not_enough_history(db_session):
    status = check_feature_drift(db_session, model_name="xgboost_match_result")
    assert status.has_enough_history is False
    assert status.drift_detected is False


def test_feature_drift_missing_summary_on_older_runs(db_session):
    db_session.add_all(
        [
            TrainingRun(
                model_name="xgboost_match_result",
                status="success",
                metrics={"accuracy": 0.5, "log_loss": 1.0},  # no feature_summary at all
                started_at=datetime(2024, 1, 1),
            ),
            _training_run(
                "xgboost_match_result",
                {"elo_diff": {"mean": 10.0, "std": 5.0}},
                datetime(2024, 2, 1),
            ),
        ]
    )
    db_session.commit()

    status = check_feature_drift(db_session, model_name="xgboost_match_result")
    assert status.has_enough_history is False


def test_feature_drift_detects_a_large_shift(db_session):
    db_session.add_all(
        [
            _training_run(
                "xgboost_match_result",
                {
                    "elo_diff": {"mean": 10.0, "std": 5.0},
                    "home_rest_days": {"mean": 6.0, "std": 2.0},
                },
                datetime(2024, 1, 1),
            ),
            _training_run(
                "xgboost_match_result",
                # elo_diff moved 4 std devs; home_rest_days barely moved.
                {
                    "elo_diff": {"mean": 30.0, "std": 5.0},
                    "home_rest_days": {"mean": 6.2, "std": 2.0},
                },
                datetime(2024, 2, 1),
            ),
        ]
    )
    db_session.commit()

    status = check_feature_drift(db_session, model_name="xgboost_match_result")
    assert status.has_enough_history is True
    assert status.drift_detected is True
    shifted_names = {s.feature for s in status.shifted_features}
    assert "elo_diff" in shifted_names
    assert "home_rest_days" not in shifted_names


def test_feature_drift_none_when_stable(db_session):
    same_summary = {"elo_diff": {"mean": 10.0, "std": 5.0}}
    db_session.add_all(
        [
            _training_run("xgboost_match_result", same_summary, datetime(2024, 1, 1)),
            _training_run("xgboost_match_result", same_summary, datetime(2024, 2, 1)),
        ]
    )
    db_session.commit()

    status = check_feature_drift(db_session, model_name="xgboost_match_result")
    assert status.drift_detected is False
