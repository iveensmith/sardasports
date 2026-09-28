"""Injury ORM model — synced from a real external source (API-Football), never fabricated.

Each sync run for a team replaces that team's rows with the current
snapshot (injuries/suspensions change status day to day; we care about
"what's true now," not a historical log — `synced_at` on the row plus
`Team.injuries_synced_at` are enough to tell a caller how fresh the data is).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Injury(Base):
    """One player's current injury/suspension entry for a team, as reported by
    the external source at `synced_at`."""

    __tablename__ = "injuries"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)

    player_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # "Missing Fixture" | "Questionable" | "Injury" | "Suspension" (source-reported, verbatim)
    injury_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    fixture_external_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fixture_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    source: Mapped[str] = mapped_column(String(40), default="api-football", nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Injury(team_id={self.team_id}, player={self.player_name!r}, reason={self.reason!r})"
        )
