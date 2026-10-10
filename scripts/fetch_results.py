"""Fetch final scores for fixtures this engine has already predicted.

`scripts/fetch_upcoming_fixtures.py` inserts scheduled fixtures with no
score and `status="scheduled"`. Nothing has ever gone back afterward to fill
in what actually happened — every fixture ingested that way stays
`"scheduled"` forever, even weeks after it kicked off. That is the single
biggest gap in this pipeline: the board can predict a fixture and grade
*history*, but it could never grade the fixture it just predicted, and the
live track record (`app/services/progress_service.py`) could never start,
because nothing ever gave it a completed match to settle.

This closes the loop the same way `fetch_upcoming_fixtures.py` opened it —
one request per date, at API-Football's `/fixtures` endpoint — matched back
to our row by fixture id (`external_id = "apif-{id}"`). Matching by id
rather than by team name means there is no fuzzy matching to get wrong: the
row already exists, this only fills in what happened to it.

**Only the score.** Corners and cards need a second request per fixture
(`/fixtures/statistics`), and several of our competitions record neither
stat anyway — a corners call on one of those has always resolved VOID (see
`app/services/settlement.py`) and will keep doing so for these matches too.
Pulling statistics is a deliberate follow-up, not an oversight: the score is
what makes a board honest, and it is what this fetches.

**The 90-minute score, not extra time.** A fixture that went to extra time
or penalties gets its *full-time* score from API-Football's `score.fulltime`
block, matching the convention Football-Data.co.uk already uses for the
historical data this engine trained on — a cup final that finished 1-1 after
90 and 2-1 after extra time is stored as 1-1, the same result shape as every
other match in the database.

Usage:
    uv run python scripts/fetch_results.py            # last 3 days
    uv run python scripts/fetch_results.py --days 10  # a paid plan's wider window

A free API-Football plan only serves a short rolling window around today —
in practice about three days back — and returns an explicit "not available
on this plan" response for anything older, which `fetch_date` already
treats as "nothing here" rather than an error. The default below matches
that window so a normal run doesn't spend a request-and-a-warning on every
date it already knows will fail; raise `--days` if a wider plan allows it.
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, datetime, timedelta

import requests

from app.database.session import SessionLocal
from app.models.match import Match
from app.utils.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REQUEST_DELAY_SECONDS = 1.0

# Fixture statuses API-Football uses for a match that has a final result.
# "AET"/"PEN" still carry a `score.fulltime` (the 90-minute score) alongside
# the extra-time result, which is what gets stored — see the module
# docstring. Postponed/cancelled/abandoned fixtures are deliberately left
# alone: there is no real score to grade them against, and API-Football
# generally reschedules them under the same fixture id rather than issuing a
# new one, so a later run picks them up once they are actually played.
FINISHED_STATUSES = {"FT", "AET", "PEN"}


def fetch_date(target_date, api_key: str, base_url: str, timeout: int = 40) -> list[dict]:
    """Every fixture API-Football lists for one date, unfiltered.

    Same endpoint and one-request-per-date shape as
    `fetch_upcoming_fixtures.fetch_date` — this only differs in which
    fixtures it keeps out of the response.
    """
    response = requests.get(
        f"{base_url}/fixtures",
        headers={"x-apisports-key": api_key},
        params={"date": target_date.isoformat()},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        if isinstance(errors, dict) and "plan" in errors:
            logger.warning("%s not available on this plan (%s)", target_date, errors["plan"])
            return []
        raise SystemExit(f"API-Football error for {target_date}: {errors}")
    return payload.get("response", [])


def results_from_fixtures(items: list[dict]) -> dict[str, dict]:
    """Finished fixtures, keyed by the `external_id` we stored them under.

    Returns only fixtures API-Football considers finished, with the 90-minute
    score and half-time score pulled out. A fixture missing either score
    entirely (a malformed response, or a status API-Football hasn't
    documented) is skipped rather than stored as a 0-0 — a genuinely
    unscored "finished" fixture is a data problem, not a scoreline.
    """
    results: dict[str, dict] = {}
    for item in items:
        fixture = item.get("fixture") or {}
        if fixture.get("status", {}).get("short") not in FINISHED_STATUSES:
            continue
        fixture_id = fixture.get("id")
        if fixture_id is None:
            continue

        score = item.get("score") or {}
        fulltime = score.get("fulltime") or {}
        home_score, away_score = fulltime.get("home"), fulltime.get("away")
        if home_score is None or away_score is None:
            # Fall back to the top-level goals block, which some historical
            # API-Football responses used before `score.fulltime` existed.
            goals = item.get("goals") or {}
            home_score, away_score = goals.get("home"), goals.get("away")
        if home_score is None or away_score is None:
            continue

        halftime = score.get("halftime") or {}
        results[f"apif-{fixture_id}"] = {
            "home_score": int(home_score),
            "away_score": int(away_score),
            "home_ht_goals": halftime.get("home"),
            "away_ht_goals": halftime.get("away"),
        }
    return results


def apply_results(session, results: dict[str, dict]) -> int:
    """Fill in the score for every scheduled match these results cover.

    Only touches rows still `status="scheduled"` — a match already marked
    completed (e.g. backfilled from a different source) is left as-is rather
    than overwritten by this one.
    """
    if not results:
        return 0

    matches = (
        session.query(Match)
        .filter(Match.external_id.in_(list(results)), Match.status == "scheduled")
        .all()
    )
    updated = 0
    for match in matches:
        result = results[match.external_id]
        match.home_score = result["home_score"]
        match.away_score = result["away_score"]
        match.home_ht_goals = result["home_ht_goals"]
        match.away_ht_goals = result["away_ht_goals"]
        match.status = "completed"
        updated += 1
    return updated


def fetch_and_apply_results(days_back: int = 3) -> int:
    """Walk backward from today, filling in results for anything finished.

    The core entry point — `main()` below is a thin CLI wrapper around this,
    and `app.scheduler.fetch_results_job` calls it directly, the same
    separation used by `sync_injuries_job`/`evaluate_predictions_job`.

    Rebuilds Elo history when anything was actually updated, so the newly
    completed matches feed into every prediction from the next request
    onward rather than sitting in the database inert until someone
    remembers to run `scripts/load_to_db.py`.
    """
    settings = get_settings()
    if not settings.api_football_key:
        raise SystemExit("API_FOOTBALL_KEY is not set. Add it to .env — see docs/setup_guide.md.")

    today = datetime.now(UTC).date()
    all_results: dict[str, dict] = {}
    for offset in range(days_back, -1, -1):
        target = today - timedelta(days=offset)
        items = fetch_date(target, settings.api_football_key, settings.api_football_base_url)
        day_results = results_from_fixtures(items)
        all_results.update(day_results)
        logger.info("%s: %d fixtures listed, %d finished", target, len(items), len(day_results))
        time.sleep(REQUEST_DELAY_SECONDS)

    if not all_results:
        logger.info("No finished fixtures found in the last %d day(s).", days_back)
        return 0

    session = SessionLocal()
    try:
        updated = apply_results(session, all_results)
        if updated:
            # Import here, not at module load: load_to_db pulls in pandas and
            # the full ORM at import time, which every other script in this
            # file's import chain would otherwise pay for even when unused.
            from scripts.load_to_db import rebuild_elo_history

            rebuild_elo_history(session, get_settings())
        session.commit()
    finally:
        session.close()

    logger.info(
        "Marked %d fixture(s) completed (of %d finished fixtures matched to our database).",
        updated,
        len(all_results),
    )
    return updated


# API-Football accepts at most this many ids in one `/fixtures?ids=` request.
IDS_PER_REQUEST = 20
# How far back stale fixtures are chased. Older than this and a fixture that never got a result
# was most likely postponed or called off, and asking about it again every run would spend the
# quota on a question that keeps getting the same answer.
STALE_LOOKBACK_DAYS = 60


def stale_scheduled_ids(session, older_than_days: int, now: datetime | None = None) -> list[str]:
    """API-Football ids of fixtures that should have finished long ago but are still scheduled.

    "Long ago" is past the rolling window `fetch_and_apply_results` can reach by date: a fixture
    still scheduled beyond it was missed (the backend was off for the days it was reachable) and
    the by-date fetch will never see it again.
    """
    now = now or datetime.now(UTC).replace(tzinfo=None)
    rows = (
        session.query(Match.external_id)
        .filter(
            Match.sport == "football",
            Match.status == "scheduled",
            Match.external_id.like("apif-%"),
            Match.match_date < now - timedelta(days=older_than_days),
            Match.match_date >= now - timedelta(days=STALE_LOOKBACK_DAYS),
        )
        .order_by(Match.match_date.asc())
        .all()
    )
    return [external_id.removeprefix("apif-") for (external_id,) in rows]


def resolve_stale_fixtures(older_than_days: int = 3, max_requests: int = 5) -> int:
    """Look up fixtures the by-date fetch missed, by id. Needs a paid plan.

    A free plan refuses the `ids` parameter outright, so the first request only comes back with
    that refusal; this returns 0 on it rather than raising, and spends nothing more.
    Returns how many fixtures were settled.
    """
    settings = get_settings()
    if not settings.api_football_key:
        return 0
    session = SessionLocal()
    try:
        ids = stale_scheduled_ids(session, older_than_days)
        if not ids:
            return 0
        results: dict[str, dict] = {}
        batches = [ids[i : i + IDS_PER_REQUEST] for i in range(0, len(ids), IDS_PER_REQUEST)]
        for batch in batches[:max_requests]:
            response = requests.get(
                f"{settings.api_football_base_url}/fixtures",
                headers={"x-apisports-key": settings.api_football_key},
                params={"ids": "-".join(batch)},
                timeout=40,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                logger.warning("Stale fixtures not available: %s", payload["errors"])
                break
            results.update(results_from_fixtures(payload.get("response", [])))
            time.sleep(REQUEST_DELAY_SECONDS)
        updated = apply_results(session, results)
        if updated:
            from scripts.load_to_db import rebuild_elo_history

            rebuild_elo_history(session, settings)
        session.commit()
        logger.info("Settled %d of %d stale fixture(s).", updated, len(ids))
        return updated
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill in results for scheduled fixtures that have finished"
    )
    parser.add_argument(
        "--days", type=int, default=3, help="How many days back to check, including today"
    )
    args = parser.parse_args()
    fetch_and_apply_results(days_back=args.days)


if __name__ == "__main__":
    main()
