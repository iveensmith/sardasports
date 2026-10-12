"""GET /board — the prediction board as a table, for any date.

The existing `/predictions/today` answers "what does the engine think about
today's card, and how much did its estimators agree?". This answers a
different question: "show me a day's fixtures the way a reader browses them"
— grouped by competition, filterable by country, with a pick in each market
column, and every past fixture graded.

It is a separate route rather than a change to that one, because that one is
still serving and its shape is part of a contract. Two endpoints over the
same data is cheaper than a migration nobody asked for.

The date parameter is what makes the board browsable backwards. Yesterday's
card is the most valuable page on a prediction site and the one most sites
quietly omit: it is where the picks are already settled, so it is the only
page a reader can use to decide whether to believe the others.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, get_db
from app.models.match import Match
from app.models.team import Team
from app.services.base_rates import competition_base_rates
from app.services.board_service import build_row, is_won
from app.services.recent_results import DEFAULT_LIMIT, MAX_LIMIT, recent_settled
from app.services.stored_predictions import predict_with_stored_fallback
from app.utils.coalesce import CoalescingCache
from ml.competition_catalogue import meta_for

router = APIRouter(tags=["board"])

# A generous ceiling rather than a page size. A busy Saturday runs to several
# hundred fixtures and a reader expects the whole day, not page one of six;
# the cap exists so a malformed request cannot ask for the entire database.
MAX_FIXTURES = 400

# A finished board is the same for every reader, so it is built once and shared for
# this long, and a burst of identical requests (the home page asks for three days at
# once, and Next prefetches) shares that one build instead of each starting its own.
# Short, because a score arriving or a price being fetched should reach the page
# within the time a reader would notice.
BOARD_CACHE_SECONDS = 30.0
# After those 30 seconds a board is still served at once, while one background rebuild replaces
# it. Rebuilding is cheap on its own (about a second) but the engine is one process that is also
# running the scheduler's jobs, and a request that landed on a rebuild during one of them waited
# 40 seconds. A visitor now sees a board at most this much older than fresh, never a wait.
# Four minutes, the interval of the warm-up job that rebuilds the boards: a score or a LIVE badge
# now reaches the page within one warm-up, where ten minutes of staleness showed a match as not
# started long after it had.
BOARD_STALE_SECONDS = 240.0
_board_cache = CoalescingCache(BOARD_CACHE_SECONDS, stale_seconds=BOARD_STALE_SECONDS)


def _day_bounds(target: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target, datetime.min.time())
    return start, start + timedelta(days=1)


@router.get("/board")
def board(
    on_date: date | None = Query(
        None, description="Day to show, YYYY-MM-DD. Defaults to today (UTC)."
    ),
    country: str | None = Query(None, description="Filter to one country or confederation."),
    competition: str | None = Query(None),
    # Football unless another sport is asked for: this is the football board, and the
    # other sports now have fixtures in the same table.
    sport: str | None = Query("football"),
    limit: int = Query(MAX_FIXTURES, ge=1, le=MAX_FIXTURES),
    db: Session = Depends(get_db),
) -> dict:
    """A day's fixtures, grouped by competition, every market called and graded."""
    target = on_date or datetime.now(UTC).date()
    return _board_cache.get_or_compute(
        (target, country, competition, sport, limit),
        # Its own session, not the request's: a stale answer is refreshed after this request
        # has finished and its session has been closed.
        lambda: _build_board_isolated(target, country, competition, sport, limit),
    )


def _build_board_isolated(
    target: date, country: str | None, competition: str | None, sport: str | None, limit: int
) -> dict:
    session = SessionLocal()
    try:
        return _build_board(session, target, country, competition, sport, limit)
    finally:
        session.close()


def _build_board(
    db: Session,
    target: date,
    country: str | None,
    competition: str | None,
    sport: str | None,
    limit: int,
) -> dict:
    start, end = _day_bounds(target)

    query = db.query(Match).filter(Match.match_date >= start, Match.match_date < end)
    if sport:
        query = query.filter(Match.sport == sport)
    if competition:
        query = query.filter(Match.competition == competition)
    matches = query.order_by(Match.match_date.asc(), Match.id.asc()).limit(limit).all()

    # The country sidebar counts the whole day, before the country filter is
    # applied — a sidebar that renumbered itself on every click would be
    # unusable.
    country_counts: dict[str, int] = defaultdict(int)
    for match in matches:
        meta = meta_for(match.competition)
        if meta:
            country_counts[meta.country] += 1

    if country:
        matches = [
            m
            for m in matches
            if (meta_for(m.competition) or None) and meta_for(m.competition).country == country
        ]

    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    names = {t.id: t.name for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
    # The board reads only the markets and the confidence, so a stored prediction that
    # is still current is as good as a fresh one and costs nothing to serve.
    predictions = predict_with_stored_fallback(db, matches, allow_stored=True)
    rows = [
        build_row(
            match,
            prediction,
            # Judged against its own competition's rates: see `competition_base_rates`.
            competition_base_rates(db, match.competition),
            names.get(match.home_team_id, ""),
            names.get(match.away_team_id, ""),
        )
        for match, prediction in zip(matches, predictions, strict=True)
    ]

    # Grouped by competition, in the order the day's first fixture in each
    # appears — so a reader scanning down the page moves forward in time
    # rather than alphabetically through leagues.
    groups: dict[str, dict] = {}
    for row in rows:
        name = row["competition"]["name"]
        groups.setdefault(name, {"competition": row["competition"], "rows": []})
        groups[name]["rows"].append(row)

    played = [r for r in rows if r["score"] is not None]
    # A refunded draw (draw no bet) or an unrecorded statistic is void: not a win and not a
    # loss, so it is out of the rate. `finished` stays "matches that have a score".
    settled = [r for r in played if (r["best_tip"] or {}).get("outcome") in ("won", "lost")]
    strong_played = [r for r in settled if r["best_tip"].get("strong")]
    return {
        "date": target.isoformat(),
        "counts": {
            # Fixtures the engine produced a prediction for, out of everything
            # scheduled. The gap is competitions with no trained model, and it
            # is reported rather than hidden.
            "fixtures": len(rows),
            "predicted": sum(1 for r in rows if r["best_tip"] is not None),
            "upcoming": sum(1 for r in rows if r["score"] is None),
            "finished": len(played),
            "settled": len(settled),
            "won": sum(1 for r in settled if is_won(r)),
            # The tips the engine rated 70% or more before kick-off: a subset of the above.
            "strong_finished": len(strong_played),
            "strong_won": sum(1 for r in strong_played if is_won(r)),
        },
        "countries": [
            {
                "country": name,
                "country_code": next(
                    (
                        meta_for(m.competition).country_code
                        for m in matches
                        if meta_for(m.competition) and meta_for(m.competition).country == name
                    ),
                    None,
                ),
                "count": count,
            }
            for name, count in sorted(country_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "groups": list(groups.values()),
    }


@router.get("/board/dates")
def board_dates(
    span: int = Query(3, ge=1, le=7, description="Days either side of today."),
    min_settled: int = Query(
        1,
        ge=1,
        le=100,
        description="Fewest finished football matches a day needs to count as 'last settled'.",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """The date strip: a few days back and forward, with fixture counts.

    Counted rather than assumed, so a day with no football is shown as empty
    instead of leading a reader to a blank page.
    """
    today = datetime.now(UTC).date()
    days = []
    for offset in range(-span, span + 1):
        target = today + timedelta(days=offset)
        start, end = _day_bounds(target)
        total = (
            db.query(Match)
            .filter(Match.sport == "football", Match.match_date >= start, Match.match_date < end)
            .count()
        )
        days.append(
            {
                "date": target.isoformat(),
                "offset": offset,
                # "%-d" is a glibc extension and raises on Windows, so the
                # day number is formatted rather than strftime'd.
                "label": {-1: "Yesterday", 0: "Today", 1: "Tomorrow"}.get(
                    offset, f"{target.strftime('%b')} {target.day}"
                ),
                "fixtures": total,
            }
        )
    # The most recent day with enough settled results on it. The home page uses
    # it for the results strip, and "enough" is the point: the newest day with
    # *any* result is routinely a day with one match on it (the tail of a
    # weekend, or the first scores to arrive), and a strip bound to that has
    # nothing to show and disappears. Football only, because only football
    # matches get a pick to grade.
    day = func.date(Match.match_date)
    newest = (
        db.query(day)
        .filter(
            Match.status == "completed",
            Match.home_score.is_not(None),
            Match.sport == "football",
        )
        .group_by(day)
        .having(func.count(Match.id) >= min_settled)
        .order_by(day.desc())
        .first()
    )

    return {
        "today": today.isoformat(),
        "days": days,
        "last_settled": newest[0] if newest else None,
    }


# Matches in play, as they are right now. Cached for seconds, not minutes: the point of the
# page that reads this is that a goal shows up within the poll that saw it.
LIVE_CACHE_SECONDS = 10.0
_live_cache = CoalescingCache(LIVE_CACHE_SECONDS, stale_seconds=60.0)


def _build_live_isolated() -> dict:
    from app.services.live_scores import FRESH_FOR

    session = SessionLocal()
    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        matches = (
            session.query(Match)
            .filter(
                Match.sport == "football",
                Match.status == "scheduled",
                Match.live_home.is_not(None),
                Match.live_updated_at >= now - FRESH_FOR,
            )
            .order_by(Match.match_date.asc(), Match.id.asc())
            .all()
        )
        team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
        names = (
            {t.id: t.name for t in session.query(Team).filter(Team.id.in_(team_ids)).all()}
            if team_ids
            else {}
        )
        predictions = predict_with_stored_fallback(session, matches, allow_stored=True)
        rows = [
            build_row(
                match,
                prediction,
                competition_base_rates(session, match.competition),
                names.get(match.home_team_id, ""),
                names.get(match.away_team_id, ""),
            )
            for match, prediction in zip(matches, predictions, strict=True)
        ]
        # Only rows whose live view is really there (a stale one reads as not live).
        rows = [r for r in rows if r.get("live")]
        return {"count": len(rows), "as_of": now.isoformat(), "rows": rows}
    finally:
        session.close()


@router.get("/board/live")
def board_live() -> dict:
    """Football matches in play right now, with minute and score, each with its stored tip."""
    return _live_cache.get_or_compute("live", _build_live_isolated)


@router.get("/board/recent-settled")
def board_recent_settled(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
) -> dict:
    """The newest graded best tips across recent days, for the home results strip.

    Read from stored predictions, so it needs no recomputation and does not
    depend on any one day having enough finished matches.
    """
    return recent_settled(db, limit)
