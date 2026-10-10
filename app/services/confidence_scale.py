"""The confidence score as a rank, so it spreads fixtures out instead of bunching them.

The engine's raw confidence (0 to 100) measures how closely its three estimators agree, and
for football it sits between about 89 and 98 for nine fixtures in ten. Shown as "9.1 out of 10"
beside "9.6 out of 10" it tells a reader almost nothing, even though it carries a signal: over
two thousand graded picks, those in the most agreed-on fifth won 81% of the time and those in
the least agreed-on fifth 72%.

So the board shows where a fixture's raw confidence ranks among every football prediction the
engine has stored, scaled to ten: 5 is the median, 9 or more is in the top tenth. The order
is exactly the raw confidence's order, so nothing about which fixture is more agreed-on
changes, and a rank cannot be mistaken for a probability. If too few predictions are stored
to rank against, the raw score over ten is used, as before.
"""

from __future__ import annotations

import bisect
import logging

from app.database.session import SessionLocal
from app.models import Match, Prediction
from app.utils.coalesce import CoalescingCache

logger = logging.getLogger(__name__)

# Below this many stored predictions a rank means little, so the raw score is shown instead.
MIN_SAMPLES = 300
_SCALE = CoalescingCache(600, max_entries=1, max_concurrent=1, copy_results=False)


def _load() -> list[float]:
    session = SessionLocal()
    try:
        rows = (
            session.query(Prediction.confidence)
            .join(Match, Match.id == Prediction.match_id)
            .filter(Match.sport == "football", Prediction.confidence.is_not(None))
            .all()
        )
        return sorted(float(c) for (c,) in rows)
    except Exception:  # noqa: BLE001 - the raw score is a fine fallback; never fail a board
        logger.exception("could not load the confidence scale")
        session.rollback()
        return []
    finally:
        session.close()


def rank_out_of_ten(confidence: float | None) -> float | None:
    """`confidence`'s rank among stored football predictions, 0 to 10; None if unrankable."""
    if confidence is None:
        return None
    scale = _SCALE.get_or_compute("football", _load)
    if len(scale) < MIN_SAMPLES:
        return None
    below = bisect.bisect_left(scale, confidence)
    at_or_below = bisect.bisect_right(scale, confidence)
    # Ties share the middle of their range, so a score that many predictions share is not
    # pushed to either end.
    return round(10.0 * (below + at_or_below) / 2 / len(scale), 1)
