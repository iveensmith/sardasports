"""A basketball or tennis prediction, stored before the match so it can be graded.

Football keeps its predictions in `predictions`, whose columns are shaped around a
three-way result and goal markets. These two sports have no draw and a different
total, so they get their own small table rather than a football row with invented
columns. Every probability here is a **percentage** (0 to 100), named `_pct` so that
nothing has to guess the scale: football's table mixes fractions and percentages and
that has already caused one wrong published record.

A row is written while the match is still ahead, and it is not changed once kick-off
is close, so a graded row is what the engine really said in advance. `created_at` is
when it was first stored; a row whose `created_at` is later than the match's start was
made afterwards and is never counted as a live pick.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class SportPrediction(Base):
    __tablename__ = "sport_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), unique=True, index=True)
    sport: Mapped[str] = mapped_column(String(20), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    home_win_pct: Mapped[float] = mapped_column(Float)
    away_win_pct: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # The total (points in basketball, games in tennis) is offered at the line closest
    # to a coin flip. All three are null when no total could be priced for the match.
    total_line: Mapped[float | None] = mapped_column(Float, nullable=True)
    prob_over_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_total: Mapped[float | None] = mapped_column(Float, nullable=True)

    model_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The full engine output at the time, for the match page and for audit.
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
