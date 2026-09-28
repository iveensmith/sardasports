"""GET /elo/{team} — current Elo rating and its full history for a team."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Team
from app.schemas.elo import EloHistoryPointOut, EloOut
from app.services.elo_service import get_team_elo_history
from app.utils.team_names import normalize_team_name

router = APIRouter(tags=["elo"])


@router.get("/elo/{team}", response_model=EloOut)
def get_elo(team: str, db: Session = Depends(get_db)) -> EloOut:
    name = normalize_team_name(team)
    team_obj = db.query(Team).filter(Team.name == name).one_or_none()
    if team_obj is None:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found")

    history_rows = get_team_elo_history(db, team_obj)
    id_to_name = {t.id: t.name for t in db.query(Team).all()}

    history = [
        EloHistoryPointOut(
            match_date=row.match_date,
            rating_before=row.rating_before,
            rating_after=row.rating_after,
            opponent=id_to_name.get(row.opponent_team_id),
            was_home=row.was_home,
        )
        for row in history_rows
    ]
    return EloOut(team=team_obj.name, current_rating=team_obj.elo_rating, history=history)
