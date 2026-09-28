"""Team-related response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    league: str | None
    elo_rating: float


class TeamFormSummary(BaseModel):
    matches_played: int
    wins: int
    draws: int
    losses: int
    goals_scored: int
    goals_conceded: int
    clean_sheets: int
    points_per_game: float


class RecentMatchOut(BaseModel):
    match_id: int
    match_date: datetime
    competition: str
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None


class TeamDetailOut(BaseModel):
    team: TeamOut
    form_last5: TeamFormSummary
    form_last10: TeamFormSummary
    recent_matches: list[RecentMatchOut]
