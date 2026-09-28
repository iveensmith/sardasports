"""Injuries response schema."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InjuryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_name: str
    injury_type: str | None
    reason: str | None
    fixture_date: datetime | None


class InjuriesOut(BaseModel):
    team: str
    available: bool
    synced_at: datetime | None
    injuries: list[InjuryOut]
    message: str | None = None
