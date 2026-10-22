"""POST /analyst/{match_id} — the AI analyst agent's narrative for a match.

Requires ANTHROPIC_API_KEY in the environment; returns 503 (not a crash) if
it isn't configured, so the rest of the API keeps working without it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.analyst import AgentNotConfiguredError, generate_analysis
from app.api.deps_auth import get_viewer
from app.database.session import get_db
from app.models import Match, Team
from app.schemas.analyst import AnalystOut
from app.services import access

router = APIRouter(tags=["analyst"])


@router.post("/analyst/{match_id}", response_model=AnalystOut)
def get_analysis(
    match_id: int,
    db: Session = Depends(get_db),
    viewer: access.Viewer = Depends(get_viewer),
) -> AnalystOut:
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

    home_team = db.get(Team, match.home_team_id)
    away_team = db.get(Team, match.away_team_id)

    try:
        result = generate_analysis(db, match_id, home_team.name, away_team.name)
    except AgentNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return AnalystOut(
        match_id=match_id,
        analysis=result.analysis,
        tool_calls=result.tool_calls,
        model=result.model,
    )
