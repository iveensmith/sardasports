"""GET /fixtures/today — fixtures scheduled for a given date (default: today)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Match, Team
from app.schemas.fixture import FixtureOut, FixturesResponse

router = APIRouter(tags=["fixtures"])


@router.get("/fixtures/today", response_model=FixturesResponse)
def get_fixtures_today(
    on_date: date | None = Query(default=None, description="Defaults to today (UTC) if omitted"),
    db: Session = Depends(get_db),
) -> FixturesResponse:
    target_date = on_date or datetime.now(UTC).date()
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)

    matches = (
        db.query(Match)
        .filter(Match.sport == "football", Match.match_date >= start, Match.match_date < end)
        .order_by(Match.match_date.asc())
        .all()
    )
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    id_to_name = {t.id: t.name for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}

    fixtures = [
        FixtureOut(
            match_id=m.id,
            match_date=m.match_date,
            competition=m.competition,
            home_team=id_to_name[m.home_team_id],
            away_team=id_to_name[m.away_team_id],
            status=m.status,
        )
        for m in matches
    ]
    return FixturesResponse(date=target_date.isoformat(), count=len(fixtures), fixtures=fixtures)
