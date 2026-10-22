"""GET /history/{match_id} — prediction timeline for a match (how the prediction evolved)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps_auth import get_viewer
from app.database.session import get_db
from app.models import Match
from app.schemas.prediction import PredictionHistoryOut, PredictionHistoryPointOut
from app.services import access
from app.services.prediction_service import get_prediction_timeline

router = APIRouter(tags=["history"])


@router.get("/history/{match_id}", response_model=PredictionHistoryOut)
def get_history(
    match_id: int,
    db: Session = Depends(get_db),
    viewer: access.Viewer = Depends(get_viewer),
) -> PredictionHistoryOut:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
    if access.match_is_locked(db, match, viewer):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "locked",
                "message": "This prediction is for premium members until the match kicks off.",
            },
        )

    rows = get_prediction_timeline(db, match_id)
    timeline = [
        PredictionHistoryPointOut(
            home_win=round(row.prob_home * 100, 1),
            draw=round(row.prob_draw * 100, 1),
            away_win=round(row.prob_away * 100, 1),
            confidence=row.confidence,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return PredictionHistoryOut(match_id=match_id, timeline=timeline)
