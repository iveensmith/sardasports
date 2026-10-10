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

import logging
from time import monotonic

from sqlalchemy.orm import Session, joinedload

from app.models.match import Match
from app.models.prediction import Prediction
from app.services.base_rates import competition_base_rates
from app.services.board_service import build_row
from app.services.stored_predictions import payload_from_stored

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 24
MAX_LIMIT = 60
# Below this the website hides the strip (more gap than content). Keep in step with
# MIN_STRIP_ITEMS in web/lib/api.ts; the canary in app/scheduler.py shouts when the
# data falls under it.
MIN_STRIP_ITEMS = 4

# The strip is the home page's proof, and it must not blink out because one
# database read failed. So the last good answer is kept in memory:
#
# * for CACHE_TTL_SECONDS it is served without touching the database at all, which
#   also takes load off the one component that is hit on every home-page render;
# * after that it is recomputed, and if the recompute fails (a lock, an exhausted
#   connection pool) the previous answer is served again, marked `stale`, rather
#   than an error. A strip that is a minute out of date is invisible to a reader; a
#   missing one is the first thing they notice.
#
# Only when there has never been a good answer does a failure surface as an error,
# and the website then falls back on its own copy (see web/lib/api.ts).
CACHE_TTL_SECONDS = 120
_cache: dict[int, tuple[float, dict]] = {}


def clear_cache() -> None:
    """For tests, and for anything that has just changed what the strip should show."""
    _cache.clear()


def recent_settled(session: Session, limit: int = DEFAULT_LIMIT) -> dict:
    """The newest graded best tips, newest first, with the dates they span."""
    limit = max(1, min(limit, MAX_LIMIT))
    cached = _cache.get(limit)
    if cached is not None and monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    try:
        result = _compute(session, limit)
    except Exception:
        logger.exception("recent-settled recompute failed")
        # A failed statement leaves the session unusable until it is rolled back.
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        if cached is not None:
            return {**cached[1], "stale": True}
        raise

    _cache[limit] = (monotonic(), result)
    return result


def refresh(session: Session, limit: int = DEFAULT_LIMIT) -> dict:
    """Recompute now and store the result, ignoring the freshness window.

    For the background canary, so the strip's data is rebuilt on a schedule and a
    visitor's request almost always finds it fresh. A failure raises and leaves the
    previous good answer in place.
    """
    limit = max(1, min(limit, MAX_LIMIT))
    result = _compute(session, limit)
    _cache[limit] = (monotonic(), result)
    return result


def _compute(session: Session, limit: int) -> dict:
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
            competition_base_rates(session, match.competition),
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
