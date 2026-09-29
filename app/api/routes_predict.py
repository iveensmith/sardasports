"""GET /predict/{match_id} — full ensemble prediction for one fixture."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.prediction import (
    BasketballPredictionOut,
    PredictionOut,
    TennisPredictionOut,
)
from app.services.base_rates import market_base_rates
from app.services.prediction_service import MatchNotFoundError, predict_for_match
from ml.markets import best_per_market, candidate_calls, headline_call, rank_calls

router = APIRouter(tags=["predictions"])


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
    ranked = rank_calls(
        candidate_calls(payload, payload["home_team"], payload["away_team"]),
        market_base_rates(db, "football"),
    )
    best = headline_call(ranked)
    payload["calls"] = {
        "headline": best.as_dict() if best else None,
        "by_market": [entry.as_dict() for entry in best_per_market(ranked)],
    }
    return PredictionOut(**payload)
