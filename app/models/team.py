"""Team ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Team(Base):
    """A competitor, identified by its normalized name within its sport.

    "Team" is the football-era name for this row; it also holds basketball
    franchises and individual tennis players, which is why `name` is unique
    per sport rather than globally — the same string can legitimately name a
    football club and a basketball franchise, and nothing should silently
    merge two different competitors' rating histories.
    """

    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("sport", "name", name="uq_teams_sport_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[str] = mapped_column(String(20), default="football", nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    league: Mapped[str | None] = mapped_column(String(80), nullable=True)
    elo_rating: Mapped[float] = mapped_column(default=1500.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # External-provider ID mapping and sync bookkeeping for injuries (see
    # app/models/injury.py, scripts/sync_injuries.py). Nullable: most teams
    # won't have this resolved until a sync has actually run for them.
    api_football_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    injuries_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Team(id={self.id}, name={self.name!r})"
