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
    # Display-only counts, not used by any training pipeline — see
    # ml.feature_engineering.features.compute_goal_rate_form.
    over_1_5: int
    over_2_5: int
    over_3_5: int
    btts: int


class SeasonStatOut(BaseModel):
    """One stat's per-match average, this season. `sample_size` is how many
    of this season's matches actually reported it — `value` is `None` when
    that's zero, never a fabricated 0.0."""

    value: float | None
    sample_size: int


class SeasonStatsOut(BaseModel):
    """Season averages beyond goals (already on `TeamFormSummary`) — shots,
    corners, cards, and the three fields only `scripts/fetch_match_stats.py`
    can fill (possession, offsides, fouls). See
    `app.services.team_service.compute_season_stat_averages`."""

    season: str
    matches_played: int
    shots: SeasonStatOut
    shots_on_target: SeasonStatOut
    corners: SeasonStatOut
    cards: SeasonStatOut
    possession: SeasonStatOut
    offsides: SeasonStatOut
    fouls: SeasonStatOut


class RecentMatchOut(BaseModel):
    match_id: int
    match_date: datetime
    competition: str
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    # None where the source never recorded a half-time score, not a
    # fabricated 0-0 — see docs/architecture.md's "Half-time goals" section.
    home_ht_score: int | None
    away_ht_score: int | None


class TeamDetailOut(BaseModel):
    team: TeamOut
    form_last5: TeamFormSummary
    form_last10: TeamFormSummary
    recent_matches: list[RecentMatchOut]
    # None only for a team with no completed match history at all.
    season_stats: SeasonStatsOut | None = None
