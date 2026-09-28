"""Prediction ORM models.

`Prediction` holds the current/latest prediction snapshot per match (upserted
whenever a fresh prediction is computed). `PredictionHistory` is an append-only
log of every snapshot ever produced for a match, which is what a prediction
timeline (Monday 54% -> Wednesday 58% -> matchday 61%) is built from.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class _PredictionFields:
    """Mixin describing the fields shared by Prediction and PredictionHistory."""

    prob_home: Mapped[float] = mapped_column(Float, nullable=False)
    prob_draw: Mapped[float] = mapped_column(Float, nullable=False)
    prob_away: Mapped[float] = mapped_column(Float, nullable=False)

    expected_goals_home: Mapped[float] = mapped_column(Float, nullable=False)
    expected_goals_away: Mapped[float] = mapped_column(Float, nullable=False)

    top_scorelines: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["2-1", "1-0", ...]

    prob_btts_yes: Mapped[float] = mapped_column(Float, nullable=False)
    prob_btts_no: Mapped[float] = mapped_column(Float, nullable=False)

    # Each a list of {"line", "prob_over", "prob_under", "model_used"}, one
    # entry per offered line (see ml.prediction.predict.GOALS_LINES/
    # HT_GOALS_LINES/CORNERS_LINES/CARDS_LINES) — a JSON list rather than
    # fixed columns because the line set is a market-design choice, not a
    # fixed schema fact (adding a line later shouldn't need a migration).
    # prob_over/prob_under within an entry can be None: not every stat is
    # recorded for every league (MLS, for all four; the Saudi Pro League
    # historically for corners/cards/half-time — see docs/architecture.md's
    # "Corners and cards" and "Half-time goals" sections), so the market is
    # genuinely unavailable for some matches rather than just unpredicted.
    goals_markets: Mapped[list] = mapped_column(JSON, default=list)
    ht_goals_markets: Mapped[list] = mapped_column(JSON, default=list)
    corners_markets: Mapped[list] = mapped_column(JSON, default=list)
    cards_markets: Mapped[list] = mapped_column(JSON, default=list)

    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0-100
    confidence_label: Mapped[str] = mapped_column(default="Low")

    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id"), nullable=True
    )


class Prediction(Base, _PredictionFields):
    """Most recent prediction for a match (one row per match)."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id"), unique=True, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PredictionHistory(Base, _PredictionFields):
    """Append-only log of every prediction snapshot computed for a match."""

    __tablename__ = "prediction_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Set once the match completes, for error analysis (Step 6 of the spec).
    actual_home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
