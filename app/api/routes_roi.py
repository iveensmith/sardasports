"""GET /model/roi-backtest — retrospective flat-staking simulation over held-out matches.

This is expensive: it recomputes a full ensemble prediction (including a
from-scratch Poisson refit against all prior history) for every held-out
match with odds — live-measured at ~2 minutes against the current EPL
2022-25 dataset with no cache running. That's long enough to time out most
HTTP clients/proxies, so results are cached (same pattern as `/predict`,
just a much longer TTL since this only changes when models are retrained
or new data is ingested — recomputing it on every request would make the
endpoint effectively unusable).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.roi import BacktestResultOut
from app.utils.cache import get_cache
from ml.monitoring.roi_backtest import run_backtest

router = APIRouter(tags=["model"])

CACHE_TTL_SECONDS = 3600


@router.get("/model/roi-backtest", response_model=BacktestResultOut)
def get_roi_backtest(
    edge_threshold: float = Query(
        default=5.0,
        ge=0,
        le=100,
        description="Minimum model-vs-market edge, in percentage points, to place a bet",
    ),
    stake: float = Query(default=1.0, gt=0, description="Flat stake per bet, in arbitrary units"),
    db: Session = Depends(get_db),
) -> BacktestResultOut:
    cache = get_cache()
    cache_key = f"roi-backtest:{edge_threshold}:{stake}"
    cached = cache.get_json(cache_key)
    if cached is not None:
        return BacktestResultOut(**cached)

    result = run_backtest(db, edge_threshold=edge_threshold, stake=stake)
    payload = BacktestResultOut(**result.__dict__)
    cache.set_json(cache_key, payload.model_dump(mode="json"), ttl_seconds=CACHE_TTL_SECONDS)
    return payload
