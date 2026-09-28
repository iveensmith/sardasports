"""Fixture list response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FixtureOut(BaseModel):
    match_id: int
    match_date: datetime
    competition: str
    home_team: str
    away_team: str
    status: str


class FixturesResponse(BaseModel):
    date: str
    count: int
    fixtures: list[FixtureOut]
