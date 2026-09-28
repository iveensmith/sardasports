"""GET /predictions/today — every upcoming fixture with its prediction.

An additive endpoint: it composes the existing `/fixtures/today` and
`/predict/{id}` behaviour and changes neither. It exists because calling
them separately is quadratic in practice — `/predict/{id}` loads the
sport's entire completed history to build its baselines, so a 40-fixture
board re-read ~64,000 football rows forty times and took minutes.

`predict_for_matches` groups by (sport, date) and loads that history once
per group. The predictions are identical to the per-match route's; only the
number of table scans changes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Match, Team
from app.services.prediction_service import predict_for_matches

router = APIRouter(tags=["predictions"])


@router.get("/predictions/today")
def predictions_today(
    on_date: date | None = Query(default=None, description="Defaults to today (UTC)"),
    sport: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """Fixtures for a date, each with its prediction where one is possible.

    `prediction` is null for a fixture the engine could not price. That is
    reported per fixture rather than dropped, so the board can say what it
    could not do instead of silently showing a shorter list.
    """
    target = on_date or datetime.now(UTC).date()
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)

    query = db.query(Match).filter(Match.match_date >= start, Match.match_date < end)
    if sport:
        query = query.filter(Match.sport == sport)
    matches = query.order_by(Match.match_date.asc()).limit(limit).all()

    predictions = predict_for_matches(db, matches)

    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    names = {t.id: t.name for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}

    return {
        "date": target.isoformat(),
        "count": len(matches),
        "predicted": sum(1 for p in predictions if p is not None),
        "fixtures": [
            {
                "match_id": m.id,
                "match_date": m.match_date.isoformat(),
                "sport": m.sport,
                "competition": m.competition,
                "home_team": names.get(m.home_team_id, ""),
                "away_team": names.get(m.away_team_id, ""),
                "status": m.status,
                "prediction": prediction,
            }
            for m, prediction in zip(matches, predictions, strict=True)
        ],
    }
