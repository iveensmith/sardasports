"""GET /matches and GET /competitions — browsing support.

Every other endpoint needs a `match_id` you already have, or an exact date
you know has fixtures. Nothing lets a caller (the dashboard, primarily)
discover one from scratch — these two endpoints close that gap.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Match, Team
from app.schemas.match_browse import CompetitionOut, CompetitionsOut, MatchesOut, MatchSummaryOut
from app.utils.team_names import normalize_team_name

router = APIRouter(tags=["matches"])


@router.get("/matches", response_model=MatchesOut)
def list_matches(
    competition: str | None = None,
    season: str | None = None,
    team: str | None = None,
    sport: str | None = None,
    status: str | None = Query(default=None, pattern="^(scheduled|completed)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> MatchesOut:
    query = db.query(Match)
    if sport:
        query = query.filter(Match.sport == sport)
    if competition:
        query = query.filter(Match.competition == competition)
    if season:
        query = query.filter(Match.season == season)
    if status:
        query = query.filter(Match.status == status)
    if team:
        # Team names are unique per *sport*, not globally, so a bare
        # `.one_or_none()` on the name would raise MultipleResultsFound the
        # first time a name existed in two sports. Match every competitor
        # with that name (narrowed by `sport` when the caller gave one).
        team_query = db.query(Team).filter(Team.name == normalize_team_name(team))
        if sport:
            team_query = team_query.filter(Team.sport == sport)
        team_ids = [t.id for t in team_query.all()]
        if not team_ids:
            return MatchesOut(count=0, limit=limit, offset=offset, matches=[])
        query = query.filter(
            or_(Match.home_team_id.in_(team_ids), Match.away_team_id.in_(team_ids))
        )

    total = query.count()
    rows = query.order_by(Match.match_date.desc()).offset(offset).limit(limit).all()

    team_ids = {m.home_team_id for m in rows} | {m.away_team_id for m in rows}
    id_to_name = {t.id: t.name for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}

    matches = [
        MatchSummaryOut(
            match_id=m.id,
            match_date=m.match_date,
            sport=m.sport,
            competition=m.competition,
            season=m.season,
            home_team=id_to_name[m.home_team_id],
            away_team=id_to_name[m.away_team_id],
            home_score=m.home_score,
            away_score=m.away_score,
            status=m.status,
            has_odds=m.odds_home_win is not None,
        )
        for m in rows
    ]
    return MatchesOut(count=total, limit=limit, offset=offset, matches=matches)


@router.get("/competitions", response_model=CompetitionsOut)
def list_competitions(sport: str | None = None, db: Session = Depends(get_db)) -> CompetitionsOut:
    query = db.query(Match.sport, Match.competition, Match.season).distinct()
    if sport:
        query = query.filter(Match.sport == sport)

    by_competition: dict[tuple[str, str], set[str]] = {}
    for row_sport, competition, season in query.all():
        by_competition.setdefault((row_sport, competition), set()).add(season)

    match_counts: dict[tuple[str, str], int] = {
        (row_sport, competition): db.query(Match)
        .filter(Match.sport == row_sport, Match.competition == competition)
        .count()
        for (row_sport, competition) in by_competition
    }

    competitions = [
        CompetitionOut(
            competition=competition,
            sport=row_sport,
            seasons=sorted(seasons),
            match_count=match_counts[(row_sport, competition)],
        )
        for (row_sport, competition), seasons in sorted(
            by_competition.items(), key=lambda kv: (kv[0][0], kv[0][1])
        )
    ]
    return CompetitionsOut(competitions=competitions)
