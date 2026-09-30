"""Match event ORM model — one goal, synced from a real external source
(API-Football), never fabricated.

Football only, and only for a match this engine has already fetched a
result for. There is no comparable event feed wired up for basketball or
tennis, so those sports simply have no rows here rather than an invented
approximation.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class MatchEvent(Base):
    """One goal in a completed match, in chronological order."""

    __tablename__ = "match_events"
    __table_args__ = (Index("ix_match_events_match_id", "match_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)

    minute: Mapped[int] = mapped_column(Integer, nullable=False)
    # Stoppage-time minutes, e.g. the "2" in "45+2" — None outside stoppage time.
    added_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # "home" | "away"
    player: Mapped[str] = mapped_column(String(120), nullable=False)
    assist: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Source-reported, verbatim: "Normal Goal" | "Penalty" | "Own Goal", ...
    detail: Mapped[str] = mapped_column(String(40), nullable=False)

    # The running score right after this goal, so a reader (or the frontend)
    # never has to replay the list to know what the score was at minute 60.
    home_score_after: Mapped[int] = mapped_column(Integer, nullable=False)
    away_score_after: Mapped[int] = mapped_column(Integer, nullable=False)

    source: Mapped[str] = mapped_column(String(40), default="api-football", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"MatchEvent(match_id={self.match_id}, minute={self.minute}, player={self.player!r})"
