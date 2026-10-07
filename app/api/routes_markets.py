"""GET /markets/{kind} — one market's picks for a day, with its own record."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.market_page_service import SPECS, build_market_page

router = APIRouter(tags=["markets"])


@router.get("/markets/{kind}")
def market_page(
    kind: str,
    on_date: date | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    if kind not in SPECS:
        raise HTTPException(status_code=404, detail=f"No market page called '{kind}'")
    target = on_date or datetime.now(UTC).date()
    return build_market_page(db, kind, datetime.combine(target, datetime.min.time()))
