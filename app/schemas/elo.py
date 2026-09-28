"""Elo-related response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EloHistoryPointOut(BaseModel):
    match_date: datetime
    rating_before: float
    rating_after: float
    opponent: str | None
    was_home: bool


class EloOut(BaseModel):
    team: str
    current_rating: float
    history: list[EloHistoryPointOut]
