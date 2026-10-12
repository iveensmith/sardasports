"""Live scores for football fixtures in play.

Until this existed a football fixture had no in-play state: it read as "not played" from kick-off
until the by-date results job saw it finished, which on a free plan is up to six hours later.

API-Football's `/fixtures?live=all` returns every fixture in play, with its minute and score, in
one request. This reads that and keeps it in five columns of its own on `matches` (`live_*`),
**separate from `home_score`/`away_score`**. That separation is the point: those two columns mean
"the final result" everywhere (grading, Elo, history), and a half-played 1-0 must never be
mistaken for one. A live score is display-only, goes stale on its own, and disappears the moment
the match is settled.

Matches are found by the id the fixture was ingested under (`apif-{id}`), so a live row can never
create or duplicate a fixture, only decorate one we already have.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import requests
from sqlalchemy.orm import Session

from app.models.match import Match

logger = logging.getLogger(__name__)

# API-Football statuses for a fixture that is being played (or is paused mid-game).
LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"}

# A live score older than this is not shown: it is a score from a poll that has since stopped
# (the match ended, the backend was off), and showing it as live would be a lie.
FRESH_FOR = timedelta(minutes=20)

# Only poll when something could be in play: a fixture that kicked off within this window and
# has no result yet. Outside it a poll would spend a request to be told nothing.
KICKED_OFF_WITHIN = timedelta(hours=3)

LABELS = {"HT": "HT", "BT": "Break", "P": "Pens", "SUSP": "Suspended", "INT": "Interrupted"}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def parse_live(items: list[dict]) -> dict[str, dict]:
    """In-play fixtures keyed by the `external_id` we store them under.

    Anything without a status in `LIVE_STATUSES`, or without both goal counts, is skipped: a
    half-known score is worse than none. A goalless game reports 0, not None, so a missing
    value really is missing.
    """
    live: dict[str, dict] = {}
    for item in items:
        fixture = item.get("fixture") or {}
        status = (fixture.get("status") or {}).get("short")
        if status not in LIVE_STATUSES or fixture.get("id") is None:
            continue
        goals = item.get("goals") or {}
        home, away = goals.get("home"), goals.get("away")
        if home is None or away is None:
            continue
        live[f"apif-{fixture['id']}"] = {
            "status": status,
            "minute": (fixture.get("status") or {}).get("elapsed"),
            "home": int(home),
            "away": int(away),
        }
    return live


def apply_live(session: Session, live: dict[str, dict], now: datetime | None = None) -> int:
    """Store the live view on the matching scheduled fixtures; clear it where it has ended.

    Returns how many fixtures were updated. A row that was live but is no longer in the feed
    has its live columns cleared, so it falls back to "not played" until its result is settled.
    """
    now = now or _utcnow()
    updated = 0
    if live:
        for match in (
            session.query(Match)
            .filter(
                Match.sport == "football",
                Match.status == "scheduled",
                Match.external_id.in_(list(live)),
            )
            .all()
        ):
            view = live[match.external_id]
            match.live_status = view["status"]
            match.live_minute = view["minute"]
            match.live_home = view["home"]
            match.live_away = view["away"]
            match.live_updated_at = now
            updated += 1

    # Anything we showed as live that this poll did not return has finished or stopped.
    stale = session.query(Match).filter(
        Match.live_updated_at.is_not(None),
        Match.live_updated_at < now,
    )
    if live:
        stale = stale.filter(~Match.external_id.in_(list(live)))
    for match in stale.all():
        match.live_status = match.live_minute = match.live_home = match.live_away = None
        match.live_updated_at = None
    return updated


def live_payload(match: Match, now: datetime | None = None) -> dict | None:
    """What a board row or match page shows for a fixture in play, or None.

    None when the fixture is already settled, when it has no live data, or when that data is
    older than `FRESH_FOR`.
    """
    # getattr: callers (and tests) pass lightweight stand-ins that lack these columns.
    updated_at = getattr(match, "live_updated_at", None)
    home = getattr(match, "live_home", None)
    if match.status != "scheduled" or updated_at is None or home is None:
        return None
    now = now or _utcnow()
    if now - updated_at > FRESH_FOR:
        return None
    status = getattr(match, "live_status", None)
    minute = getattr(match, "live_minute", None)
    label = LABELS.get(status) or (f"{minute}'" if minute is not None else "Live")
    return {
        "status": status,
        "minute": minute,
        "label": label,
        "home": home,
        "away": getattr(match, "live_away", 0),
    }


def needs_live_poll(session: Session, now: datetime | None = None) -> bool:
    """True if some football fixture could be in play right now."""
    now = now or _utcnow()
    return (
        session.query(Match.id)
        .filter(
            Match.sport == "football",
            Match.status == "scheduled",
            Match.external_id.like("apif-%"),
            Match.match_date <= now + timedelta(minutes=5),
            Match.match_date >= now - KICKED_OFF_WITHIN,
        )
        .first()
        is not None
    )


def fetch_live_items(api_key: str, base_url: str, timeout: int = 40) -> list[dict]:
    """Every fixture API-Football reports in play, in one request."""
    response = requests.get(
        f"{base_url}/fixtures",
        headers={"x-apisports-key": api_key},
        params={"live": "all"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        logger.warning("Live scores not available: %s", payload["errors"])
        return []
    return payload.get("response", [])


# A fixture that left the live feed is looked up by id so its final score lands within a poll of
# the whistle. Only fixtures that kicked off within this window are considered: older ones belong
# to the results job.
ENDED_LOOKBACK = timedelta(hours=5)
# A fixture that never showed as live is only asked about once it could plausibly be over.
COULD_BE_OVER_AFTER = timedelta(minutes=100)
# API-Football accepts up to 20 ids per `ids` request.
IDS_PER_REQUEST = 20


def ended_candidates(session: Session, live: dict, now: datetime | None = None) -> list[str]:
    """Fixtures that should now have finished but are not in the live feed.

    Either they were showing as live and have dropped out of the feed (full time), or they
    kicked off long enough ago to be over. Their ids, without the `apif-` prefix.
    """
    now = now or _utcnow()
    query = session.query(Match.external_id, Match.live_updated_at, Match.match_date).filter(
        Match.sport == "football",
        Match.status == "scheduled",
        Match.external_id.like("apif-%"),
        Match.match_date >= now - ENDED_LOOKBACK,
        Match.match_date <= now,
    )
    out = []
    for external_id, live_at, kickoff in query.all():
        if external_id in live:
            continue
        if live_at is not None or kickoff <= now - COULD_BE_OVER_AFTER:
            out.append(external_id.removeprefix("apif-"))
    return out


def fetch_fixtures_by_id(
    api_key: str, base_url: str, ids: list[str], timeout: int = 40
) -> list[dict]:
    """The given fixtures, in as few requests as the id limit allows. Needs a paid plan."""
    items: list[dict] = []
    for start in range(0, len(ids), IDS_PER_REQUEST):
        batch = ids[start : start + IDS_PER_REQUEST]
        response = requests.get(
            f"{base_url}/fixtures",
            headers={"x-apisports-key": api_key},
            params={"ids": "-".join(batch)},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            logger.warning("Fixtures by id not available: %s", payload["errors"])
            break
        items.extend(payload.get("response", []))
    return items


def refresh_live_scores(
    session: Session, api_key: str, base_url: str, *, lookup_ended: bool = False
) -> dict:
    """One poll: store the live view, and settle any fixture that has just finished.

    The live feed lists only matches in play, so a match that ends simply vanishes from it. On a
    paid plan (`lookup_ended`) every fixture that vanished, or kicked off long enough ago to be
    over, is looked up by id in the same poll, so the final score and the graded tip land
    within a couple of minutes of full time and not at the next results run. A fixture can also
    appear in the live feed itself with a finished status; those are settled here too.
    """
    from app.services.prediction_service import _WRITE_LOCK
    from scripts.fetch_results import apply_results, results_from_fixtures

    items = fetch_live_items(api_key, base_url)
    live = parse_live(items)
    ended: list[str] = []
    if lookup_ended:
        # Before `apply_live` clears the live view of whatever is no longer in the feed.
        ended = ended_candidates(session, live)
    ended_items: list[dict] = []
    if ended:
        try:
            ended_items = fetch_fixtures_by_id(api_key, base_url, ended)
        except requests.RequestException as exc:
            logger.warning("Looking up ended fixtures failed: %s", exc)
    # SQLite takes one writer at a time and a board storing predictions is a writer too. Taking
    # the engine's own write lock first makes this queue in Python, where waiting is free, rather
    # than spend the database's busy timeout (see `prediction_service._WRITE_LOCK`).
    with _WRITE_LOCK:
        updated = apply_live(session, live)
        settled = apply_results(session, results_from_fixtures(items + ended_items))
        session.commit()
    return {
        "in_play": len(live),
        "updated": updated,
        "settled": settled,
        "looked_up": len(ended),
    }
