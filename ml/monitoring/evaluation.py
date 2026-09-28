"""Post-match prediction evaluation.

Step 6 of the spec ("fetch result, compare prediction, calculate error") —
this module backfills the actual result onto every `prediction_history` row
for a match once that match completes, which is the data calibration and
drift monitoring are computed from. Pure DB read/write; no modeling logic
lives here.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Match, PredictionHistory
from app.utils.logging import get_logger

logger = get_logger(__name__)


def backfill_actual_results(session: Session) -> int:
    """Fill in `actual_home_goals`/`actual_away_goals` for completed matches.

    Only touches `prediction_history` rows that don't have an actual result
    recorded yet. Returns the number of rows updated.
    """
    rows = (
        session.query(PredictionHistory, Match)
        .join(Match, Match.id == PredictionHistory.match_id)
        .filter(
            Match.status == "completed",
            PredictionHistory.actual_home_goals.is_(None),
        )
        .all()
    )

    for history_row, match in rows:
        history_row.actual_home_goals = match.home_score
        history_row.actual_away_goals = match.away_score

    if rows:
        session.commit()
    logger.info("Backfilled actual results for %d prediction_history rows", len(rows))
    return len(rows)


def actual_result_label(home_score: int, away_score: int) -> str:
    """ "home_win" | "draw" | "away_win" for a completed match's actual scoreline."""
    if home_score > away_score:
        return "home_win"
    if home_score < away_score:
        return "away_win"
    return "draw"


def predicted_result_label(prob_home: float, prob_draw: float, prob_away: float) -> str:
    """The outcome the model assigned the highest probability to."""
    probs = {"home_win": prob_home, "draw": prob_draw, "away_win": prob_away}
    return max(probs, key=probs.get)
