"""GET /standings/{competition} — live league table computed from ingested results."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.standings import StandingsOut
from app.services.standings_service import compute_standings

router = APIRouter(tags=["standings"])


@router.get("/standings/{competition}", response_model=StandingsOut)
def get_standings(
    competition: str,
    season: str | None = Query(default=None, description="Defaults to the most recent season"),
    db: Session = Depends(get_db),
) -> StandingsOut:
    resolved_season, table = compute_standings(db, competition, season)
    if not table:
        raise HTTPException(
            status_code=404,
            detail=f"No completed matches found for competition '{competition}'"
            + (f" season '{season}'" if season else ""),
        )
    return StandingsOut(competition=competition, season=resolved_season, table=table)
