"""FastAPI application factory and entrypoint.

Run with: `uv run uvicorn app.main:app --reload`
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    routes_analyst,
    routes_board,
    routes_board_table,
    routes_discover,
    routes_elo,
    routes_fixtures,
    routes_history,
    routes_injuries,
    routes_leaderboard,
    routes_matches,
    routes_model,
    routes_monitoring,
    routes_predict,
    routes_progress,
    routes_retrain,
    routes_roi,
    routes_standings,
    routes_team,
    routes_value,
)
from app.scheduler import start_scheduler, stop_scheduler
from app.utils.config import get_settings
from app.utils.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()  # no-op unless ENABLE_SCHEDULER=true (see app/scheduler.py)
    yield
    stop_scheduler()


app = FastAPI(
    title="UniquePredict",
    description="AI-powered football prediction engine — Elo + Poisson + XGBoost ensemble.",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Minimal in-process rate limiting -------------------------------------
# A fixed-window limiter per client IP. Good enough for a single-process
# deployment; swap for a Redis-backed limiter (app.utils.cache already gives
# you a Redis client) before running multiple API replicas.
_request_log: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = _request_log[client_ip]
    window[:] = [t for t in window if now - t < 60]

    if len(window) >= settings.api_rate_limit_per_minute:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    window.append(now)
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "env": settings.app_env}


app.include_router(routes_fixtures.router)
app.include_router(routes_board.router)
app.include_router(routes_board_table.router)
app.include_router(routes_progress.router)
app.include_router(routes_discover.router)
app.include_router(routes_leaderboard.router)
app.include_router(routes_predict.router)
app.include_router(routes_team.router)
app.include_router(routes_elo.router)
app.include_router(routes_history.router)
app.include_router(routes_retrain.router)
app.include_router(routes_model.router)
app.include_router(routes_value.router)
app.include_router(routes_monitoring.router)
app.include_router(routes_analyst.router)
app.include_router(routes_standings.router)
app.include_router(routes_roi.router)
app.include_router(routes_injuries.router)
app.include_router(routes_matches.router)

# Dashboard: plain HTML/CSS/JS served as static files, calling the JSON API
# above via fetch() — no build step, no extra dependency. See
# app/static/dashboard/README.md.
app.mount("/dashboard", StaticFiles(directory="app/static/dashboard", html=True), name="dashboard")
