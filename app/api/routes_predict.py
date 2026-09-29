"""GET /predict/{match_id} — full ensemble prediction for one fixture."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.routes_board import agreement_for
from app.database.session import get_db
from app.models.match import Match
from app.schemas.prediction import (
    BasketballPredictionOut,
    PredictionOut,
    TennisPredictionOut,
)
from app.services.base_rates import market_base_rates
from app.services.pick_service import best_pick
from app.services.prediction_service import MatchNotFoundError, predict_for_match
from ml.markets import best_per_market, candidate_calls, headline_call, rank_calls

router = APIRouter(tags=["predictions"])


def _completed_matches(db: Session, team_id: int | None) -> int | None:
    """How much history a competitor has, for the thin-evidence guard.

    A rating built from ten matches sits near the 1500 default, so an "edge"
    measured against it is model error rather than value.
    """
    if team_id is None:
        return None
    return (
        db.query(func.count(Match.id))
        .filter(
            Match.status == "completed",
            or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
        )
        .scalar()
    )


@router.get(
    "/predict/{match_id}",
    response_model=PredictionOut | BasketballPredictionOut | TennisPredictionOut,
)
def predict(
    match_id: int, db: Session = Depends(get_db)
) -> PredictionOut | BasketballPredictionOut | TennisPredictionOut:
    """The prediction for one match, in that sport's own shape.

    The response model is a union rather than one schema with optional
    fields: a basketball game has no draw probability and no goal markets,
    and modelling that as `draw: float | None` would make a real football
    value and a not-applicable-in-this-sport value indistinguishable to any
    client. `sport` discriminates the two.
    """
    try:
        payload = predict_for_match(db, match_id)
    except MatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    sport = payload.get("sport")
    if sport == "basketball":
        return BasketballPredictionOut(**payload)
    if sport == "tennis":
        return TennisPredictionOut(**payload)

    # Football is the fall-through, and the football payload does not carry a
    # `sport` key at all — `PredictionOut.sport` defaults it. So this must be
    # keyed off "not one of the others" exactly as the branches above are,
    # never off `sport == "football"`, which is never true here.
    #
    # Every market this fixture supports, not just the match result. Computed
    # in the route rather than the service because it needs the base-rate
    # table, which is a property of the whole database rather than of one
    # prediction.
    ranked = rank_calls(candidate_calls(payload), market_base_rates(db, "football"))
    best = headline_call(ranked)
    payload["calls"] = {
        "headline": best.as_dict() if best else None,
        "by_market": [entry.as_dict() for entry in best_per_market(ranked)],
    }

    # The market comparison. It used to live only on the board row, where it
    # competed with the prediction for attention; a page someone has opened to
    # read the analysis is where it belongs.
    match = db.get(Match, match_id)
    if match is not None:
        payload["value"] = best_pick(
            payload,
            match.odds_markets,
            agreement_for(payload),
            home_matches=_completed_matches(db, match.home_team_id),
            away_matches=_completed_matches(db, match.away_team_id),
        )
    return PredictionOut(**payload)
