"""Standings response schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StandingsRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    team: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int


class StandingsOut(BaseModel):
    competition: str
    season: str | None
    table: list[StandingsRowOut]
