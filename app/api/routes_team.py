"""GET /team/{team} — team profile: current form and recent results."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Team
from app.schemas.team import TeamDetailOut
from app.services.team_page_service import build_team_page, resolve_team, top_rated_teams
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


@router.get("/teams/{slug}")
def get_team_page(slug: str, db: Session = Depends(get_db)) -> dict:
    """A team's own page, addressed by its readable slug (`aston-villa`)."""
    team = resolve_team(db, slug)
    if team is None:
        raise HTTPException(status_code=404, detail=f"No team matches '{slug}'")
    return build_team_page(db, team)


@router.get("/teams")
def list_top_rated_teams(limit: int = Query(8, ge=1, le=50), db: Session = Depends(get_db)) -> dict:
    """The highest-rated recently active clubs, for navigation."""
    return {"teams": top_rated_teams(db, limit)}
