"""The latest settled picks, for the home page's results strip.

The strip used to be built from "the last day that settled enough matches",
fetched as a whole board. That made it fragile in two ways and it vanished more
than once. It needed a single calendar day with enough finished matches, which a
card this size does not reliably have; and it needed a full day's predictions
recomputed on the spot, so one slow or failed request hid it with nothing to say
why.

This reads stored predictions straight from the database instead. There is no
recomputation, so it is fast and cannot fail the way a live prediction can, and
it takes the newest settled picks across however many days that needs, so there is
no day-size threshold to fall below. The strip names the dates it covers, so it is
never passed off as last night's results.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models.match import Match
from app.models.prediction import Prediction
from app.services.base_rates import market_base_rates
from app.services.board_service import build_row
from app.services.stored_predictions import payload_from_stored

DEFAULT_LIMIT = 24
MAX_LIMIT = 60


def recent_settled(session: Session, limit: int = DEFAULT_LIMIT) -> dict:
    """The newest graded best tips, newest first, with the dates they span."""
    limit = max(1, min(limit, MAX_LIMIT))
    base_rates = market_base_rates(session, "football")

    # Over-fetch: a pick can come back void (a stat the match never recorded) or
    # have no headline at all, and neither belongs on a strip of settled results.
    candidates = (
        session.query(Prediction, Match)
        .join(Match, Match.id == Prediction.match_id)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(
            Match.sport == "football",
            Match.status == "completed",
            Match.home_score.is_not(None),
            Match.away_score.is_not(None),
        )
        .order_by(Match.match_date.desc())
        .limit(limit * 3)
        .all()
    )

    rows: list[dict] = []
    for prediction, match in candidates:
        row = build_row(
            match,
            payload_from_stored(prediction),
            base_rates,
            match.home_team.name,
            match.away_team.name,
        )
        tip = row["best_tip"]
        if tip is None or tip["outcome"] not in ("won", "lost"):
            continue
        rows.append(row)
        if len(rows) >= limit:
            break

    dates = [row["match_date"][:10] for row in rows]
    return {
        "count": len(rows),
        "won": sum(1 for row in rows if row["best_tip"]["outcome"] == "won"),
        "from": min(dates) if dates else None,
        "to": max(dates) if dates else None,
        "rows": rows,
    }
