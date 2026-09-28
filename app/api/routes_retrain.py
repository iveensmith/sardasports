"""POST /retrain — trigger a fresh training run for the XGBoost match-result model.

Runs synchronously and returns the new model's metrics. A failed run is
logged to `training_runs` with status="failed" rather than silently swallowed,
so `/model/performance` reflects reality even when training didn't produce a
usable model (e.g. not enough data yet).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import TrainingRun
from app.schemas.model_performance import RetrainResponse
from app.utils.logging import get_logger
from ml.training.train_match_result import MODEL_NAME, train

logger = get_logger(__name__)
router = APIRouter(tags=["training"])


@router.post("/retrain", response_model=RetrainResponse)
def retrain(db: Session = Depends(get_db)) -> RetrainResponse:
    started_at = datetime.now(UTC)
    try:
        metrics = train()
    except SystemExit as exc:
        db.add(
            TrainingRun(
                model_name=MODEL_NAME,
                status="failed",
                metrics={},
                notes=str(exc),
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        )
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Retraining failed")
        db.add(
            TrainingRun(
                model_name=MODEL_NAME,
                status="failed",
                metrics={},
                notes=str(exc),
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        )
        db.commit()
        raise HTTPException(status_code=500, detail="Training run failed") from exc

    return RetrainResponse(
        status="success", model_name=MODEL_NAME, version=metrics.get("version"), metrics=metrics
    )
