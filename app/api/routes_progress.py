"""GET /progress — the public track record.

Separate from `/model/performance`, which reports a model's own test-set
metrics. This reports what the *board* called and whether it came in, which
is the question a reader actually has.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.progress_service import build_progress

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
