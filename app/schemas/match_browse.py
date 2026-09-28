"""Match browsing / competition listing schemas — support the dashboard's
match picker, which otherwise has no way to discover a match_id."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MatchSummaryOut(BaseModel):
    match_id: int
    match_date: datetime
    # Which sport — the browser needs this to know which prediction shape
    # `/predict/{match_id}` will return for this row.
    sport: str = "football"
    competition: str
    season: str
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    status: str
    has_odds: bool


class MatchesOut(BaseModel):
    count: int
    limit: int
    offset: int
    matches: list[MatchSummaryOut]


class CompetitionOut(BaseModel):
    competition: str
    sport: str = "football"
    seasons: list[str]
    match_count: int


class CompetitionsOut(BaseModel):
    competitions: list[CompetitionOut]
