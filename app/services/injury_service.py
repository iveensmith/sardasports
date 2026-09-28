"""Injury lookup service — reads what scripts/sync_injuries.py has stored.

Pure DB reads; never calls the external API itself (that's the sync script's
job, run manually or via the scheduler). Keeps `GET /injuries/{team}` and the
AI agent's `get_injuries` tool fast and independent of API-Football's uptime.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Injury, Team


def get_team_injuries(session: Session, team: Team) -> list[Injury]:
    return (
        session.query(Injury).filter(Injury.team_id == team.id).order_by(Injury.player_name).all()
    )
