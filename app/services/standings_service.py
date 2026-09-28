"""League standings — computed live from our own ingested match results.

Unlike injuries, this needs no external data source: every completed match
we've already ingested carries a result, so a standings table is a direct,
real aggregation of data we already have, not something requiring a new feed.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Match, Team


@dataclass
class StandingsRow:
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int


def resolve_latest_season(session: Session, competition: str) -> str | None:
    latest = (
        session.query(Match.season)
        .filter(Match.competition == competition, Match.status == "completed")
        .order_by(Match.match_date.desc())
        .first()
    )
    return latest[0] if latest else None


def compute_standings(
    session: Session, competition: str, season: str | None = None
) -> tuple[str | None, list[StandingsRow]]:
    """Standard football table: sorted by points, then goal difference, then goals for.

    `season` defaults to the most recent season with completed matches in
    `competition` if not given. Returns (resolved_season, table) — the
    resolved season is `None` only if the competition has no completed
    matches at all.
    """
    if season is None:
        season = resolve_latest_season(session, competition)
        if season is None:
            return None, []

    matches = (
        session.query(Match)
        .filter(
            Match.competition == competition, Match.season == season, Match.status == "completed"
        )
        .all()
    )
    if not matches:
        return season, []

    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    id_to_name = {t.id: t.name for t in session.query(Team).filter(Team.id.in_(team_ids)).all()}

    stats: dict[str, StandingsRow] = {
        name: StandingsRow(
            team=name,
            played=0,
            won=0,
            drawn=0,
            lost=0,
            goals_for=0,
            goals_against=0,
            goal_difference=0,
            points=0,
        )
        for name in id_to_name.values()
    }

    for m in matches:
        home_name = id_to_name[m.home_team_id]
        away_name = id_to_name[m.away_team_id]
        _apply_result(stats[home_name], scored=m.home_score, conceded=m.away_score)
        _apply_result(stats[away_name], scored=m.away_score, conceded=m.home_score)

    ordered = sorted(
        stats.values(), key=lambda r: (r.points, r.goal_difference, r.goals_for), reverse=True
    )
    return season, ordered


def _apply_result(row: StandingsRow, scored: int, conceded: int) -> None:
    row.played += 1
    row.goals_for += scored
    row.goals_against += conceded
    row.goal_difference = row.goals_for - row.goals_against
    if scored > conceded:
        row.won += 1
        row.points += 3
    elif scored == conceded:
        row.drawn += 1
        row.points += 1
    else:
        row.lost += 1
