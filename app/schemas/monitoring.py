"""Value detection, calibration, and drift monitoring response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ValueEdgeOut(BaseModel):
    outcome: str
    model_probability: float
    market_implied_probability: float
    edge: float


class ValueDetectionOut(BaseModel):
    match_id: int
    home_team: str
    away_team: str
    odds_home_win: float
    odds_draw: float
    odds_away_win: float
    edges: list[ValueEdgeOut]
    disclaimer: str = (
        "Mathematical difference between the model's probability and the market's "
        "overround-adjusted implied probability. Not a profit guarantee."
    )


class CalibrationBucketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bucket_low: float
    bucket_high: float
    count: int
    mean_predicted_probability: float
    actual_accuracy: float


class CalibrationReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    num_predictions: int
    brier_score: float
    overall_accuracy: float
    buckets: list[CalibrationBucketOut]


class DriftStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_name: str
    has_enough_history: bool
    latest_accuracy: float | None
    previous_accuracy: float | None
    accuracy_delta: float | None
    latest_log_loss: float | None
    previous_log_loss: float | None
    log_loss_delta: float | None
    drift_detected: bool
    reasons: list[str]


class FeatureShiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feature: str
    previous_mean: float
    latest_mean: float
    previous_std: float
    shift: float


class FeatureDriftStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_name: str
    has_enough_history: bool
    shifted_features: list[FeatureShiftOut]
    reasons: list[str]
    drift_detected: bool


class ModelMonitoringOut(BaseModel):
    calibration: CalibrationReportOut
    drift: DriftStatusOut
    feature_drift: FeatureDriftStatusOut
