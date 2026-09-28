"""Elo query service — DB-backed lookups on top of ml.elo.engine's rating math."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import EloHistory, Team
from app.utils.config import get_settings


def get_team_elo_before(session: Session, team_id: int, before_date: datetime) -> float:
    """Elo rating for `team_id` as of just before `before_date`.

    Falls back to the configured initial rating if the team has no Elo
    history yet (e.g. it has never played a completed match).
    """
    row = (
        session.query(EloHistory)
        .filter(EloHistory.team_id == team_id, EloHistory.match_date < before_date)
        .order_by(EloHistory.match_date.desc())
        .first()
    )
    if row is not None:
        return row.rating_after
    return get_settings().elo_initial_rating


def get_team_elo_history(session: Session, team: Team) -> list[EloHistory]:
    return (
        session.query(EloHistory)
        .filter(EloHistory.team_id == team.id)
        .order_by(EloHistory.match_date.asc())
        .all()
    )
