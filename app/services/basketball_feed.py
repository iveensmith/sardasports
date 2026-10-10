"""Basketball games from API-Basketball, for every league, kept up to date.

Two ways in, because the free plan allows two different things:

* **The date feed.** `/games?date=D` returns every league's games on one day, and the
  free plan serves yesterday, today and tomorrow. One request a day-window therefore
  brings in every upcoming fixture and every fresh result across all leagues (about
  80 to 140 games a day), with no league list to maintain. This is what makes the
  site's board live, and a league appears the day the provider starts listing it.
* **The history backfill.** `/games?league=L&season=S` returns a whole season, and the
  free plan serves seasons that began in 2022 to 2024. That is what gives a league the
  results its ratings are built from. It costs one request per league-season, so it
  runs a few at a time through the day against what is left of the quota.

Both spend the provider's daily quota (100 on the free plan), and both ask the provider
how much is left before spending any (`/status` is free). If the answer cannot be read,
nothing is spent: skipping a run is cheap, a spent day is not.

Only games with a real outcome become results. A postponed, cancelled or abandoned game
is left out rather than stored half-known, and a game in play is kept as scheduled until
it finishes, so a score is never taken from a game that is still being played.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests
from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.team import Team
from app.utils.config import get_settings
from ml.basketball_catalogue import PRIORITY_IDS, catalogue, display_name, free_plan_seasons

logger = logging.getLogger(__name__)

BASE_URL = "https://v1.basketball.api-sports.io"
SPORT = "basketball"
RAW_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "basketball"

FINISHED = {"FT", "AOT"}
NOT_STARTED = {"NS"}
IN_PLAY = {"Q1", "Q2", "Q3", "Q4", "OT", "BT", "HT"}

# Requests left unspent so a script run by hand has some room.
MARGIN = 5
# The free plan allows 10 requests a minute; spacing them 6.5 s apart stays under it.
REQUEST_DELAY_SECONDS = 6.5


class RateLimited(Exception):
    """The provider's per-minute limit was hit; waiting a minute clears it."""


class PlanLimit(Exception):
    """The provider refused this request because of the account's plan."""


def _headers(settings) -> dict:
    return {"x-apisports-key": settings.api_football_key}


def requests_left(settings, timeout: int = 15) -> int | None:
    """Requests still available today, or None if the provider cannot be asked."""
    if not getattr(settings, "api_football_key", None):
        return None
    try:
        response = requests.get(f"{BASE_URL}/status", headers=_headers(settings), timeout=timeout)
        response.raise_for_status()
        body = (response.json() or {}).get("response") or {}
        used = body["requests"]["current"]
        limit = body["requests"]["limit_day"]
        return max(0, int(limit) - int(used))
    except Exception:  # noqa: BLE001 - fail closed: unknown means "do not spend"
        logger.warning("Could not read API-Basketball quota; spending nothing")
        return None


def fetch_games(settings, params: dict, timeout: int = 60) -> list[dict]:
    response = requests.get(
        f"{BASE_URL}/games", headers=_headers(settings), params=params, timeout=timeout
    )
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        if isinstance(errors, dict) and "plan" in errors:
            raise PlanLimit(errors["plan"])
        if isinstance(errors, dict) and "rateLimit" in errors:
            raise RateLimited(errors["rateLimit"])
        raise RuntimeError(f"API-Basketball error {params}: {errors}")
    return payload.get("response", [])


def fetch_games_patiently(settings, params: dict) -> list[dict]:
    """`fetch_games`, waiting out the per-minute limit once before giving up."""
    try:
        return fetch_games(settings, params)
    except RateLimited:
        logger.info("basketball rate limit reached; waiting a minute")
        time.sleep(61)
        return fetch_games(settings, params)


def parse_item(item: dict) -> dict | None:
    """One API game as the columns `matches` stores, or None if it is not usable."""
    status = (item.get("status") or {}).get("short")
    home = ((item.get("teams") or {}).get("home") or {}).get("name")
    away = ((item.get("teams") or {}).get("away") or {}).get("name")
    raw_date = item.get("date")
    league = item.get("league") or {}
    if not (status and home and away and raw_date and item.get("id")):
        return None

    if status in FINISHED:
        scores = item.get("scores") or {}
        home_total = (scores.get("home") or {}).get("total")
        away_total = (scores.get("away") or {}).get("total")
        if home_total is None or away_total is None or home_total == away_total:
            return None
        # An awarded game is recorded as 20-0. It was never played, and as a score it would
        # teach the scoring averages and the totals that a team can score nothing.
        if min(home_total, away_total) <= 0:
            return None
        outcome = "completed"
    elif status in NOT_STARTED or status in IN_PLAY:
        home_total = away_total = None
        outcome = "scheduled"
    else:
        # Postponed, cancelled, suspended, awarded or abandoned: no real result.
        return None

    country = (item.get("country") or {}).get("name")
    return {
        "external_id": f"bball-{item['id']}",
        "match_date": datetime.fromisoformat(raw_date.replace("Z", "+00:00")).replace(tzinfo=None),
        "competition": display_name(league.get("id"), league.get("name") or "Basketball", country),
        "season": str(league.get("season") or ""),
        "home_team": home,
        "away_team": away,
        "home_score": None if home_total is None else int(home_total),
        "away_score": None if away_total is None else int(away_total),
        "status": outcome,
    }


def _team(session: Session, cache: dict, name: str, competition: str) -> Team:
    key = (SPORT, name)
    if key in cache:
        return cache[key]
    team = session.query(Team).filter(Team.sport == SPORT, Team.name == name).one_or_none()
    if team is None:
        team = Team(name=name, league=competition, sport=SPORT)
        session.add(team)
        session.flush()
    cache[key] = team
    return team


def upsert(session: Session, rows: list[dict]) -> dict:
    """Insert new games and bring existing ones up to date. Returns counts."""
    wanted = {r["external_id"] for r in rows}
    existing = {
        m.external_id: m
        for m in session.query(Match)
        .filter(Match.sport == SPORT, Match.external_id.in_(wanted))
        .all()
    }
    cache: dict = {}
    counts = {"inserted": 0, "completed": 0, "updated": 0}
    for row in rows:
        current = existing.get(row["external_id"])
        if current is None:
            home = _team(session, cache, row["home_team"], row["competition"])
            away = _team(session, cache, row["away_team"], row["competition"])
            match = Match(
                external_id=row["external_id"],
                sport=SPORT,
                match_date=row["match_date"],
                competition=row["competition"],
                season=row["season"],
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=row["home_score"],
                away_score=row["away_score"],
                status=row["status"],
            )
            session.add(match)
            existing[row["external_id"]] = match
            counts["inserted"] += 1
            continue
        changed = False
        if current.status == "completed" and row["status"] == "scheduled":
            # Never walk a finished game back to scheduled.
            continue
        if current.match_date != row["match_date"]:
            current.match_date = row["match_date"]
            changed = True
        if row["status"] == "completed" and current.status != "completed":
            current.status = "completed"
            current.home_score = row["home_score"]
            current.away_score = row["away_score"]
            counts["completed"] += 1
            changed = True
        if changed:
            counts["updated"] += 1
    session.flush()
    return counts


def sync_date_window(
    session: Session, settings=None, offsets: tuple[int, ...] = (-1, 0, 1)
) -> dict:
    """Pull the games for yesterday, today and tomorrow, across every league."""
    settings = settings or get_settings()
    left = requests_left(settings)
    if left is None or left < len(offsets) + MARGIN:
        return {"skipped": "no quota to spend", "requests_left": left}

    today = datetime.now(UTC).date()
    rows: list[dict] = []
    fetched = 0
    for offset in offsets:
        day = today + timedelta(days=offset)
        try:
            items = fetch_games_patiently(settings, {"date": day.isoformat()})
        except PlanLimit as limit:
            logger.warning("basketball date %s not served on this plan: %s", day, limit)
            continue
        fetched += 1
        rows.extend(r for r in map(parse_item, items) if r)
        time.sleep(REQUEST_DELAY_SECONDS)

    counts = upsert(session, rows)
    session.commit()
    counts.update({"requests": fetched, "games": len(rows)})
    return counts


def _raw_path(league_id: int, season: str) -> Path:
    return RAW_DIR / f"league{league_id}_{season}.json"


def _already_fetched(league_id: int, season: str) -> bool:
    if _raw_path(league_id, season).exists():
        return True
    if league_id == 12:  # the NBA was fetched by the first version of the script
        return (RAW_DIR / f"NBA_{season}.json").exists()
    return False


def backfill_plan() -> list[tuple[int, str]]:
    """Every (league, season) the free plan serves and that has not been fetched, best first."""
    order = list(PRIORITY_IDS) + [lid for lid in catalogue() if lid not in PRIORITY_IDS]
    plan = []
    for league_id in order:
        if catalogue()[league_id].kind == "cup" and league_id not in PRIORITY_IDS:
            continue
        for season in free_plan_seasons(league_id):
            if not _already_fetched(league_id, season):
                plan.append((league_id, season))
    return plan


def backfill(session: Session, settings=None, max_requests: int = 40) -> dict:
    """Fetch up to `max_requests` missing league-seasons, within what quota is left."""
    settings = settings or get_settings()
    left = requests_left(settings)
    if left is None or left <= MARGIN:
        return {"skipped": "no quota to spend", "requests_left": left}
    budget = min(max_requests, left - MARGIN)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    done: list[str] = []
    stopped: str | None = None
    for league_id, season in backfill_plan()[:budget]:
        try:
            items = fetch_games_patiently(settings, {"league": league_id, "season": season})
        except PlanLimit as limit:
            logger.warning("league=%s season=%s not served: %s", league_id, season, limit)
            items = []
        except Exception as exc:  # noqa: BLE001 - keep what was fetched, report why it stopped
            stopped = f"{league_id}/{season}: {exc}"
            logger.error("basketball backfill stopped at %s", stopped)
            break
        # Cached even when empty, so a league with no games that season is not asked again.
        _raw_path(league_id, season).write_text(json.dumps(items), encoding="utf-8")
        rows.extend(r for r in map(parse_item, items) if r)
        done.append(f"{league_id}/{season}:{len(items)}")
        time.sleep(REQUEST_DELAY_SECONDS)

    counts = upsert(session, rows)
    session.commit()
    counts.update({"requests": len(done), "games": len(rows), "remaining": len(backfill_plan())})
    if stopped:
        counts["stopped"] = stopped
    return counts


def load_cached_files(session: Session) -> dict:
    """Load every cached raw season file (no requests), e.g. after a database reset."""
    rows: list[dict] = []
    for path in sorted(RAW_DIR.glob("league*_*.json")):
        rows.extend(r for r in map(parse_item, json.loads(path.read_text(encoding="utf-8"))) if r)
    counts = upsert(session, rows)
    session.commit()
    return counts


__all__ = [
    "PlanLimit",
    "backfill",
    "backfill_plan",
    "fetch_games",
    "fetch_games_patiently",
    "load_cached_files",
    "parse_item",
    "requests_left",
    "sync_date_window",
    "upsert",
]
