"""GET /sports, /sports/{sport}, its board for a day, and its record."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, get_db
from app.services.sport_predictions import SPORTS, build_board, sport_record
from app.services.sport_service import sport_overview, sports_summary
from app.utils.coalesce import CoalescingCache

router = APIRouter(tags=["sports"])

# The basketball and tennis pages read a board and a record on every render. Both used to be
# rebuilt inside the request that found them expired (the record walks every graded prediction),
# so that visitor waited, and so did anyone arriving alongside. Now an entry is kept for a minute,
# then served at once for up to ten more while one background rebuild replaces it; and the
# warm-up job (`sports_warm_job`) rebuilds them every few minutes, so in practice nobody waits.
SPORTS_CACHE_SECONDS = 60.0
SPORTS_STALE_SECONDS = 600.0
_cache = CoalescingCache(SPORTS_CACHE_SECONDS, stale_seconds=SPORTS_STALE_SECONDS, max_entries=128)


def _isolated(build, *args, **kwargs):
    """Run a builder on its own session: a stale entry is refreshed after the request that
    triggered it has finished and closed its session."""
    session = SessionLocal()
    try:
        return build(session, *args, **kwargs)
    finally:
        session.close()


def board_for(sport: str, target: date, *, stored_only: bool = False) -> dict:
    return _cache.get_or_compute(
        ("board", sport, target, stored_only),
        lambda: _isolated(
            build_board,
            sport,
            datetime.combine(target, datetime.min.time()),
            stored_only=stored_only,
        ),
    )


def record_for(sport: str) -> dict:
    return _cache.get_or_compute(("record", sport), lambda: _isolated(sport_record, sport))


@router.get("/sports")
def list_sports(db: Session = Depends(get_db)) -> dict:
    return sports_summary(db)


@router.get("/sports/{sport}")
def sport_page(sport: str, db: Session = Depends(get_db)) -> dict:
    try:
        return sport_overview(db, sport)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No page for sport '{sport}'") from None


@router.get("/sports/{sport}/board")
def sport_board(
    sport: str,
    on_date: date | None = Query(None, description="Defaults to today (UTC)"),
    stored_only: bool = Query(
        False,
        description="Serve only predictions already stored; never price a match now",
    ),
) -> dict:
    """One day's matches in a sport, grouped by competition, each with its prediction."""
    if sport not in SPORTS:
        raise HTTPException(status_code=404, detail=f"No board for sport '{sport}'")
    target = on_date or datetime.now(UTC).date()
    return board_for(sport, target, stored_only=stored_only)


@router.get("/sports/{sport}/record")
def sport_record_route(sport: str) -> dict:
    """Graded predictions that were stored before the match, apart from reconstructed ones."""
    if sport not in SPORTS:
        raise HTTPException(status_code=404, detail=f"No record for sport '{sport}'")
    return record_for(sport)
