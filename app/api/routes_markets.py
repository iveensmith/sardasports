"""GET /markets/{kind} — one market's picks for a day, with its own record."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps_auth import get_viewer
from app.database.session import get_db
from app.services import access
from app.services.market_page_service import SPECS, build_market_page

router = APIRouter(tags=["markets"])


@router.get("/markets/{kind}")
def market_page(
    kind: str,
    on_date: date | None = Query(None),
    db: Session = Depends(get_db),
    viewer: access.Viewer = Depends(get_viewer),
) -> dict:
    if kind not in SPECS:
        raise HTTPException(status_code=404, detail=f"No market page called '{kind}'")
    target = on_date or datetime.now(UTC).date()
    page = build_market_page(db, kind, datetime.combine(target, datetime.min.time()))
    # Picks for matches still to be played are left out for anyone who may not see them, and
    # counted so the page can say so.
    page["picks"], page["locked_count"] = access.filter_picks(db, page["picks"], viewer)
    return page
