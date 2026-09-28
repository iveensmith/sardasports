"""GET /value/{match_id} — model probability vs. bookmaker-implied probability."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Match, Team
from app.schemas.monitoring import ValueDetectionOut
from app.services.prediction_service import MatchNotFoundError, predict_for_match
from ml.monitoring.value_detection import compute_value_edges

router = APIRouter(tags=["value"])


@router.get("/value/{match_id}", response_model=ValueDetectionOut)
def get_value(match_id: int, db: Session = Depends(get_db)) -> ValueDetectionOut:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")

    if match.odds_home_win is None or match.odds_draw is None or match.odds_away_win is None:
        raise HTTPException(
            status_code=404,
            detail=f"No bookmaker odds available for match {match_id}",
        )

    try:
        prediction = predict_for_match(db, match_id)
    except MatchNotFoundError as exc:  # pragma: no cover - already checked above
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    edges = compute_value_edges(
        model_home=prediction["home_win"],
        model_draw=prediction["draw"],
        model_away=prediction["away_win"],
        odds_home=match.odds_home_win,
        odds_draw=match.odds_draw,
        odds_away=match.odds_away_win,
    )

    home_team = db.get(Team, match.home_team_id)
    away_team = db.get(Team, match.away_team_id)

    return ValueDetectionOut(
        match_id=match.id,
        home_team=home_team.name,
        away_team=away_team.name,
        odds_home_win=match.odds_home_win,
        odds_draw=match.odds_draw,
        odds_away_win=match.odds_away_win,
        edges=[
            {
                "outcome": e.outcome,
                "model_probability": e.model_probability,
                "market_implied_probability": round(e.market_implied_probability, 1),
                "edge": round(e.edge, 1),
            }
            for e in edges
        ],
    )
