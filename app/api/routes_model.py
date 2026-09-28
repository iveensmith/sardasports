"""GET /model/performance — active model version + recent training history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import ModelVersion
from app.schemas.model_performance import ModelPerformanceOut, ModelVersionOut

router = APIRouter(tags=["model"])


@router.get("/model/performance", response_model=ModelPerformanceOut)
def get_model_performance(
    model_name: str = Query(default="xgboost_match_result"),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ModelPerformanceOut:
    versions = (
        db.query(ModelVersion)
        .filter(ModelVersion.model_name == model_name)
        .order_by(ModelVersion.trained_at.desc())
        .limit(limit)
        .all()
    )
    active = next((v for v in versions if v.is_active), None)

    return ModelPerformanceOut(
        model_name=model_name,
        active_version=ModelVersionOut.model_validate(active) if active else None,
        recent_versions=[ModelVersionOut.model_validate(v) for v in versions],
    )
