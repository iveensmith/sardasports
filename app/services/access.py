"""Who may see an upcoming football prediction: 15 a day are free, the rest are for members.

The rule, in one place so every endpoint applies the same one:

* A football match that has **not kicked off** has its prediction hidden from anyone who is not a
  premium member, unless it is one of the day's free matches.
* A match that **has kicked off** (or finished) is never hidden. The record has to be checkable by
  anyone, and a pick that is only secret until the whistle is what premium sells.
* Basketball and tennis are not limited.

Which matches are free is decided from the day's fixtures alone, never from what the engine thinks
of them, so the free set cannot be picked after seeing results or favour the strongest calls: the
15 biggest-competition fixtures first (`FREE_PRIORITY`), then by kick-off time, then by id.

The hiding is done on a *copy* of what is about to be sent. The engine caches fully built boards and
rows, and a cache that held one viewer's version would hand it to the next: so nothing in a cache is
ever hidden or unhidden, and the website's own requests (which carry no member) always get the
hidden version. A member's browser asks through an authenticated route and gets the full one.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.match import Match

FREE_DAILY_LIMIT = 15

# The competitions whose fixtures are free first, in this order; every other football competition
# follows, by kick-off time. Names are as the engine stores them.
FREE_PRIORITY: tuple[str, ...] = (
    "UEFA Champions League",
    "UEFA Europa League",
    "UEFA Conference League",
    "English Premier League",
    "Spanish La Liga",
    "Italian Serie A",
    "German Bundesliga",
    "French Ligue 1",
    "Dutch Eredivisie",
    "Portuguese Primeira Liga",
    "English Championship",
)
_RANK = {name: position for position, name in enumerate(FREE_PRIORITY)}

# The free set is read from the fixtures, which change slowly; a minute is as fresh as it needs.
FREE_SET_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class Viewer:
    """Who is asking. The website's own requests carry no member, so they are not premium."""

    premium: bool = False


ANONYMOUS = Viewer()

_cache: dict[date, tuple[float, frozenset[int]]] = {}
_lock = threading.Lock()


def clear_cache() -> None:
    """For tests, and for anything that has just changed a day's fixtures."""
    with _lock:
        _cache.clear()


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def free_match_ids(db: Session, day: date) -> frozenset[int]:
    """The football matches of a day whose predictions are free."""
    with _lock:
        hit = _cache.get(day)
        if hit is not None and hit[0] > time.monotonic():
            return hit[1]
    start = datetime.combine(day, datetime.min.time())
    rows = (
        db.query(Match.id, Match.competition, Match.match_date)
        .filter(
            Match.sport == "football",
            Match.match_date >= start,
            Match.match_date < start + timedelta(days=1),
        )
        .all()
    )
    ordered = sorted(rows, key=lambda r: (_RANK.get(r.competition, len(_RANK)), r.match_date, r.id))
    ids = frozenset(row.id for row in ordered[:FREE_DAILY_LIMIT])
    with _lock:
        _cache[day] = (time.monotonic() + FREE_SET_TTL_SECONDS, ids)
    return ids


def _is_locked(
    db: Session, *, sport: str | None, match_id: int, kickoff: datetime, now: datetime
) -> bool:
    if sport not in (None, "football"):
        return False
    if kickoff <= now:
        return False
    return match_id not in free_match_ids(db, kickoff.date())


def match_is_locked(db: Session, match: Match, viewer: Viewer) -> bool:
    """True when this viewer may not see this match's prediction."""
    if viewer.premium:
        return False
    return _is_locked(
        db, sport=match.sport, match_id=match.id, kickoff=match.match_date, now=_now()
    )


# --- hiding what is about to be sent ------------------------------------------------------------


def _is_row(node: object) -> bool:
    """A board row, wherever it turns up (a day's board, a league page, a list of bankers)."""
    return (
        isinstance(node, dict)
        and "match_id" in node
        and "tips" in node
        and "best_tip" in node
        and "odds_estimated" in node
    )


def lock_row(row: dict) -> dict:
    """A row with the prediction taken out and the bookmaker's prices left in.

    The row's "fair price" is the prediction in another form (100 over the engine's probability),
    so a price the engine worked out is removed as well as the tips: only a price a bookmaker quoted
    stays.
    """
    estimated = row.get("odds_estimated") or {}
    locked = dict(row)
    locked["tips"] = {}
    locked["best_tip"] = None
    locked["confidence"] = None
    locked["confidence_label"] = None
    locked["odds"] = {
        selection: (None if estimated.get(selection) else price)
        for selection, price in (row.get("odds") or {}).items()
    }
    locked["odds_estimated"] = dict.fromkeys(estimated, False)
    locked["locked"] = True
    return locked


def row_is_locked(db: Session, row: dict, viewer: Viewer) -> bool:
    if viewer.premium:
        return False
    return _is_locked(
        db,
        sport=row.get("sport"),
        match_id=row["match_id"],
        kickoff=datetime.fromisoformat(row["match_date"]).replace(tzinfo=None),
        now=_now(),
    )


def protect_payload(db: Session, payload, viewer: Viewer):
    """`payload` with every board row inside it hidden or marked open, as this viewer is entitled.

    A premium viewer gets the payload unchanged. Everyone else gets a copy; the original (which may
    be sitting in a cache) is not touched.
    """
    if viewer.premium:
        return payload

    def walk(node):
        if isinstance(node, list):
            return [walk(item) for item in node]
        if isinstance(node, dict):
            if _is_row(node):
                if row_is_locked(db, node, viewer):
                    return lock_row(node)
                return {**node, "locked": False}
            return {key: walk(value) for key, value in node.items()}
        return node

    return walk(payload)


def locked_match_payload(match: Match, home_team: str, away_team: str, badges: dict) -> dict:
    """What `/predict/{id}` returns for a match the viewer may not see: who is playing, when, and
    the bookmaker's prices, and nothing the engine worked out."""
    return {
        "locked": True,
        "match_id": match.id,
        "sport": "football",
        "home_team": home_team,
        "away_team": away_team,
        "match_date": match.match_date.isoformat(),
        "competition": match.competition,
        "match_status": match.status,
        "odds_1x2": (
            {"home": match.odds_home_win, "draw": match.odds_draw, "away": match.odds_away_win}
            if match.odds_home_win is not None
            or match.odds_draw is not None
            or match.odds_away_win is not None
            else None
        ),
        **badges,
    }


def filter_picks(db: Session, picks: list[dict], viewer: Viewer) -> tuple[list[dict], int]:
    """A market page's picks without the locked ones, and how many were left out.

    Dropped rather than blurred: a pick's probability is the prediction, and a list that names which
    fixtures the engine likes best, blurred or not, says a great deal about what is behind it.
    """
    if viewer.premium:
        return picks, 0
    kept = [
        pick
        for pick in picks
        if not _is_locked(
            db,
            sport="football",
            match_id=pick["match_id"],
            kickoff=datetime.fromisoformat(pick["match_date"]).replace(tzinfo=None),
            now=_now(),
        )
    ]
    return kept, len(picks) - len(kept)


def hide_entries(db: Session, entries: list[dict], viewer: Viewer) -> list[dict]:
    """The fixtures of `/predictions/today` with the engine's view removed from locked ones."""
    if viewer.premium:
        return entries
    out = []
    for entry in entries:
        locked = _is_locked(
            db,
            sport=entry.get("sport"),
            match_id=entry["match_id"],
            kickoff=datetime.fromisoformat(entry["match_date"]).replace(tzinfo=None),
            now=_now(),
        )
        if not locked:
            out.append({**entry, "locked": False})
            continue
        hidden = dict(entry)
        for key in ("prediction", "agreement", "forecast", "calls", "pick"):
            hidden[key] = None
        hidden["passed"] = False
        hidden["locked"] = True
        out.append(hidden)
    return out
