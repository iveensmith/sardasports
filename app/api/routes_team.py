"""GET /team/{team} — team profile: current form and recent results."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Team
from app.schemas.team import TeamDetailOut
from app.services.team_service import get_team_detail
from app.utils.team_names import normalize_team_name

router = APIRouter(tags=["teams"])


@router.get("/team/{team}", response_model=TeamDetailOut)
def get_team(team: str, db: Session = Depends(get_db)) -> TeamDetailOut:
    name = normalize_team_name(team)
    team_obj = db.query(Team).filter(Team.name == name).one_or_none()
    if team_obj is None:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found")

    detail = get_team_detail(db, team_obj)
    return TeamDetailOut(**detail)
