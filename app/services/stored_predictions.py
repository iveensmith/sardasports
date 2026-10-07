"""Reading predictions back out of the database, and falling back to them.

Two jobs live here because they share one fact that is easy to get wrong: the
`predictions` table stores the match-result and both-teams-to-score
probabilities as *fractions* (0.62), while the over/under, corners, cards and
half-time lines are stored as *percentages* (62.0), exactly as the engine
returns them (see `prediction_service._persist_prediction`). Everything that
ranks calls, `ml.markets`, works in percentages.

Reading a stored row without converting those fractions puts the match-result
and BTTS calls on a scale 100 times smaller than every other market, so they
can never lead. That is not hypothetical: the track record did exactly this, and
its headline call was a goals or cards pick on every row where the board's best
tip was a match result. `payload_from_stored` is the single place that
conversion happens, so no reader can get it wrong again.

The second job is resilience. Computing a prediction can fail transiently (a
database lock under load, say) and a failed computation used to leave the row
blank, which made a whole card read as having no trained model. A prediction
that was stored earlier is still a prediction the engine made, so a row falls
back to it rather than going blank.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.prediction import Prediction
from app.services.prediction_service import predict_for_matches


def _percent(fraction: float | None) -> float | None:
    """A stored 0-1 probability as the percentage the rest of the engine uses."""
    return None if fraction is None else round(float(fraction) * 100.0, 6)


def payload_from_stored(prediction: Prediction) -> dict:
    """A stored row, in the same percentage-scale shape a live prediction has.

    Carries what the board and the market pages read. It does not carry the
    per-estimator breakdown or the explanation, which are not stored.
    """
    return {
        "home_win": _percent(prediction.prob_home),
        "draw": _percent(prediction.prob_draw),
        "away_win": _percent(prediction.prob_away),
        "btts_yes": _percent(prediction.prob_btts_yes),
        "btts_no": _percent(prediction.prob_btts_no),
        "goals_markets": prediction.goals_markets or [],
        "ht_goals_markets": prediction.ht_goals_markets or [],
        "corners_markets": prediction.corners_markets or [],
        "cards_markets": prediction.cards_markets or [],
        "top_scorelines": prediction.top_scorelines or [],
        "expected_goals_home": prediction.expected_goals_home,
        "expected_goals_away": prediction.expected_goals_away,
        "confidence": prediction.confidence,
        "confidence_label": prediction.confidence_label,
    }


def predict_with_stored_fallback(session: Session, matches: list[Match]) -> list[dict | None]:
    """`predict_for_matches`, except a failed row falls back to its stored one.

    A fixture with no stored prediction and no live one stays None, which the
    board shows as unpredicted. Football only: the stored columns are football's.
    """
    results = predict_for_matches(session, matches)
    missing = [
        m.id for m, r in zip(matches, results, strict=True) if r is None and m.sport == "football"
    ]
    if not missing:
        return results

    stored = {
        row.match_id: row
        for row in session.query(Prediction).filter(Prediction.match_id.in_(missing)).all()
    }
    return [
        payload_from_stored(stored[m.id]) if r is None and m.id in stored else r
        for m, r in zip(matches, results, strict=True)
    ]
