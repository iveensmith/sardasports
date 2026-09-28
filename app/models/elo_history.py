"""Elo rating history ORM model.

Every row is a rating change produced by one match. Querying "team's Elo
before any given date" means: take the most recent row with
`match_date < target_date` and read `rating_after` (or the team's configured
initial rating if no such row exists).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class EloHistory(Base):
    """One Elo update for one team, produced by one match."""

    __tablename__ = "elo_history"
    __table_args__ = (Index("ix_elo_history_team_date", "team_id", "match_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)

    match_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    rating_before: Mapped[float] = mapped_column(nullable=False)
    rating_after: Mapped[float] = mapped_column(nullable=False)
    opponent_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    was_home: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"EloHistory(team_id={self.team_id}, {self.rating_before}->{self.rating_after})"
