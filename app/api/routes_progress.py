"""GET /progress — the public track record.

Separate from `/model/performance`, which reports a model's own test-set
metrics. This reports what the *board* called and whether it came in, which
is the question a reader actually has.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.progress_service import build_progress, daily_record_csv, matches_csv

router = APIRouter(tags=["progress"])


@router.get("/progress")
def progress(db: Session = Depends(get_db)) -> dict:
    """Every stored prediction, regraded against the final score.

    Live and backtested records are returned separately and must stay that
    way in the interface — a backtest was never exposed to the risk of being
    wrong in public, and presenting it as a published record claims credit
    the engine has not earned.
    """
    return build_progress(db)


def _csv_download(body: str, filename: str) -> Response:
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/progress/daily.csv")
def progress_daily_csv(db: Session = Depends(get_db)) -> Response:
    """The daily record: one row per day with its won/lost/void counts."""
    return _csv_download(daily_record_csv(db), "sardasports-daily-record.csv")


@router.get("/progress/matches.csv")
def progress_matches_csv(db: Session = Depends(get_db)) -> Response:
    """Every graded prediction: the call made and how the match ended."""
    return _csv_download(matches_csv(db), "sardasports-graded-matches.csv")
