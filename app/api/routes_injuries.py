"""GET /injuries/{team} — current injuries/suspensions, as last synced from API-Football."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Team
from app.schemas.injury import InjuriesOut
from app.services.injury_service import get_team_injuries
from app.utils.team_names import normalize_team_name

router = APIRouter(tags=["injuries"])


@router.get("/injuries/{team}", response_model=InjuriesOut)
def get_injuries(team: str, db: Session = Depends(get_db)) -> InjuriesOut:
    name = normalize_team_name(team)
    team_obj = db.query(Team).filter(Team.name == name).one_or_none()
    if team_obj is None:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found")

    if team_obj.injuries_synced_at is None:
        return InjuriesOut(
            team=team_obj.name,
            available=False,
            synced_at=None,
            injuries=[],
            message=(
                f"No injury data has been synced for {team_obj.name} yet. Run "
                "scripts/sync_injuries.py (requires API_FOOTBALL_KEY)."
            ),
        )

    injuries = get_team_injuries(db, team_obj)
    return InjuriesOut(
        team=team_obj.name,
        available=True,
        synced_at=team_obj.injuries_synced_at,
        injuries=injuries,
    )
