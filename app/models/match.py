"""Match ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Match(Base):
    """A single fixture/result, played or scheduled."""

    __tablename__ = "matches"
    __table_args__ = (Index("ix_matches_date_teams", "match_date", "home_team_id", "away_team_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)

    # Which sport this row is. Every football-specific column below
    # (corners/cards/half-time goals, and the goal-shaped markets built on
    # them) is meaningless for the others, so they stay nullable and are
    # reported as genuinely unavailable rather than zero-filled — the same
    # honesty rule corners/cards already follow across leagues.
    sport: Mapped[str] = mapped_column(String(20), default="football", nullable=False, index=True)

    match_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    competition: Mapped[str] = mapped_column(String(80), nullable=False)
    season: Mapped[str] = mapped_column(String(20), nullable=False)

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)

    # Renamed from home_goals/away_goals when the schema went multi-sport.
    # These hold goals for football, points for basketball, and games won
    # for tennis; the sport-specific meaning lives in `sport`.
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # True when neither side is really at home — tournament football on
    # neutral ground (World Cup, Euros) and most tennis. Both the Elo
    # home-advantage offset and the Poisson home term are wrong for these,
    # so they're applied conditionally rather than unconditionally.
    neutral_venue: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Half-time score — not every source has it (MLS's Football-Data.co.uk
    # file doesn't; see docs/architecture.md's "Half-time goals" section),
    # so nullable like the other optional match stats below.
    home_ht_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_ht_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)

    home_shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_shots_on_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_shots_on_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referee: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Possession, offsides and fouls — added alongside `match_events` below,
    # both only ever filled from API-Football's `/fixtures/statistics` for a
    # match this engine has fetched a result for (see
    # `scripts/fetch_match_stats.py`). The historical Football-Data.co.uk
    # training data never carried these three, unlike shots/corners/cards
    # above, so there is no trained model for them yet and none of this is
    # used as a training feature — it exists to answer "what actually
    # happened", not to predict it.
    home_possession: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_possession: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_offsides: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_offsides: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Set once `scripts/fetch_match_stats.py` has tried this fixture, whether
    # or not the response carried any usable stats — see that script for why
    # this can't just be "home_shots is null".
    stats_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Tennis only: "Hard" | "Clay" | "Grass" | "Carpet". Null for the other
    # sports. Surface is not cosmetic in tennis the way a pitch is in
    # football — a player's clay ability is genuinely a different quantity
    # from their hard-court ability, so ratings are kept per surface (see
    # ml/feature_engineering/tennis.py).
    surface: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Tennis only: total games won by each side.
    #
    # These are deliberately *not* in home_score/away_score, because tennis
    # is won on sets, not games: a player can win fewer games and still win
    # the match. Measured on this dataset, a games-based winner label would
    # be wrong for 2.00% of matches and undefined (an exact tie) for a
    # further 2.82% — 4.81% corrupted labels. So home_score/away_score hold
    # *sets*, keeping "higher score won" true in every sport, and games live
    # here to price the total-games market.
    home_games: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_games: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Tennis only: 3 or 5 (sets needed to win: 2 or 3). Not cosmetic — it
    # roughly sets the ceiling on total games, and the tours differ: WTA is
    # always best-of-3 (21.8 games on average) while ATP plays best-of-5 at
    # Grand Slams (25.9 overall). A totals model blind to this would price
    # a men's Slam like a regular-tour match.
    best_of: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Tennis only: the tournament this match belongs to ("Shanghai Masters"), so a day's
    # matches can be grouped by event. Null for history loaded before it was kept and for
    # every other sport.
    tournament: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Bookmaker closing odds (decimal), where the source data provides them —
    # used only for Step-5 "value detection" (comparing model vs. market
    # implied probability). Never used as a training feature: including
    # bookmaker odds as an input to the model that's meant to *compare
    # against* bookmaker odds would be circular.
    odds_home_win: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_draw: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_away_win: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Best available price per selection, across bookmakers, for the markets
    # this engine can actually price:
    #   {"match_winner": {"home": 1.18, ...},
    #    "goals": {"over_1.5": 1.24, "under_2.5": 1.9, ...},
    #    "btts": {"yes": 1.8, "no": 1.95}}
    #
    # A JSON column rather than more float columns because the set of lines
    # is not fixed — it already changed once when goals went multi-line —
    # and because a row is only ever read whole, never queried by selection.
    # The three columns above stay as they are: value detection and the ROI
    # backtest both read them, and historical rows only ever had 1X2.
    odds_markets: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    odds_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # "scheduled" | "completed"
    status: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)

    # The in-play view of a football fixture, from API-Football's live feed. Kept apart from
    # home_score/away_score on purpose: those mean "the final result" everywhere (grading, Elo,
    # history), and a half-played 1-0 must never be read as one. Display-only, goes stale on
    # its own, and is cleared when the match is settled. See app/services/live_scores.py.
    live_status: Mapped[str | None] = mapped_column(String(8), nullable=True)
    live_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    live_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    live_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    live_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])  # noqa: F821
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])  # noqa: F821

    @property
    def is_completed(self) -> bool:
        return self.home_score is not None and self.away_score is not None

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Match(id={self.id}, {self.home_team_id} vs {self.away_team_id} on {self.match_date})"
        )
