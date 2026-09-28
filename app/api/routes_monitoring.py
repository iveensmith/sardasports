"""GET /model/monitoring — calibration report + drift status (metrics and features)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.monitoring import ModelMonitoringOut
from ml.monitoring.calibration import build_calibration_report
from ml.monitoring.drift import check_drift, check_feature_drift
from ml.monitoring.evaluation import backfill_actual_results

router = APIRouter(tags=["model"])


@router.get("/model/monitoring", response_model=ModelMonitoringOut)
def get_model_monitoring(
    model_name: str = Query(default="xgboost_match_result"),
    db: Session = Depends(get_db),
) -> ModelMonitoringOut:
    backfill_actual_results(db)  # pick up any matches that completed since the last check
    calibration = build_calibration_report(db)
    drift = check_drift(db, model_name=model_name)
    feature_drift = check_feature_drift(db, model_name=model_name)
    return ModelMonitoringOut(calibration=calibration, drift=drift, feature_drift=feature_drift)
