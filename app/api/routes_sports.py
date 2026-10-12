"""GET /sports, /sports/{sport}, its board for a day, and its record."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.sport_predictions import SPORTS, build_board, sport_record
from app.services.sport_service import sport_overview, sports_summary

router = APIRouter(tags=["sports"])


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
    db: Session = Depends(get_db),
) -> dict:
    """One day's matches in a sport, grouped by competition, each with its prediction."""
    if sport not in SPORTS:
        raise HTTPException(status_code=404, detail=f"No board for sport '{sport}'")
    target = on_date or datetime.now(UTC).date()
    return build_board(
        db, sport, datetime.combine(target, datetime.min.time()), stored_only=stored_only
    )


@router.get("/sports/{sport}/record")
def sport_record_route(sport: str, db: Session = Depends(get_db)) -> dict:
    """Graded predictions that were stored before the match, apart from reconstructed ones."""
    if sport not in SPORTS:
        raise HTTPException(status_code=404, detail=f"No record for sport '{sport}'")
    return sport_record(db, sport)
