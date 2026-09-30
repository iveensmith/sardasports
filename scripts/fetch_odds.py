"""Fetch bookmaker odds for upcoming fixtures.

The board wants to say "fair price 1.30 against an offered price of 1.24",
which needs a real market price beside the model's own. Odds were never
ingested for scheduled fixtures — only historical 1X2 from
Football-Data.co.uk — so every upcoming fixture had nothing to compare
against.

**Best price per selection, across bookmakers.** A market is only as good
as the best price available in it, so taking the maximum is what makes the
comparison meaningful — an edge computed against a mediocre price would
overstate itself. Eight bookmakers typically quote each fixture.

**Only markets the engine can actually price** are kept. API-Football
returns dozens (Asian handicaps, corner 1x2, exact goals, both-halves
props); storing lines no model produces a probability for would mean a
board full of prices with nothing to compare them to.

Odds are used for comparison only. They are never a training feature —
feeding the market into a model whose job is to disagree with the market
would be circular.

Quota: one request per page per date, not per fixture — for the bulk pass.

**The bulk pass alone leaves real gaps.** `/odds?date=` paginates *every*
fixture API-Football knows about that day, most of which are competitions
this engine has never heard of, and a free plan caps that pagination at 3
pages — confirmed directly against the API, not inferred. On a day with
enough football, our own modelled fixtures simply don't all land in the
first 3 pages, and once a match kicks off there is no going back to price
it from the bulk endpoint. The result: fixtures that stayed dashes on the
board forever, odds included, even after the match had been graded.

`/odds?fixture={id}` is not paginated — a single fixture is always one
page — and directly confirmed to return real prices for fixtures the bulk
pass had missed. So after the bulk pass, this also looks up any of our own
API-Football-sourced fixtures (`external_id` starting `apif-`) in the
backfill window that still have no price, one request each, capped by
`--max-backfill` so a bad day cannot spend the whole daily quota chasing
long-tail fixtures.

Usage:
    uv run python scripts/fetch_odds.py            # today + 2 days
    uv run python scripts/fetch_odds.py --days 1
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

# Wider spacing than the bulk pass: these are individual, uncached requests
# against the free plan's per-minute cap, not one paginated call per date.
BACKFILL_DELAY_SECONDS = 3.0

# API-Football market name -> the key we store it under. Only markets this
# engine produces a probability for; everything else is dropped rather than
# stored unusable.
MARKETS = {
    "Match Winner": "match_winner",
    "Goals Over/Under": "goals",
    "Both Teams Score": "btts",
}

# Selection labels, normalised. API-Football writes "Over 2.5" and "Yes";
# the engine thinks in "over_2.5" and "yes".
SELECTIONS = {
    "home": "home",
    "draw": "draw",
    "away": "away",
    "yes": "yes",
    "no": "no",
}


def _selection_key(market_key: str, raw: str) -> str | None:
    """Normalise a bookmaker's selection label, or None if unusable."""
    value = raw.strip()
    lowered = value.lower()

    if market_key in ("match_winner", "btts"):
        return SELECTIONS.get(lowered)

    if market_key == "goals":
        parts = lowered.split()
        if len(parts) != 2 or parts[0] not in ("over", "under"):
            return None
        try:
            line = float(parts[1])
        except ValueError:
            return None
        # Quarter lines (2.25, 1.75) are Asian-style splits the engine has no
        # equivalent for — it prices whole ".5" lines only.
        if (line * 2) % 1 != 0:
            return None
        return f"{parts[0]}_{line}"

    return None


def best_prices(item: dict) -> dict:
    """Best price per selection across every bookmaker quoting this fixture."""
    out: dict[str, dict[str, float]] = {}
    for bookmaker in item.get("bookmakers") or []:
        for bet in bookmaker.get("bets") or []:
            market_key = MARKETS.get(bet.get("name", ""))
            if market_key is None:
                continue
            for value in bet.get("values") or []:
                key = _selection_key(market_key, str(value.get("value", "")))
                if key is None:
                    continue
                try:
                    price = float(value.get("odd"))
                except (TypeError, ValueError):
                    continue
                if price <= 1.0:
                    continue
                current = out.setdefault(market_key, {})
                # Max: the market is worth what its best price is worth.
                if price > current.get(key, 0.0):
                    current[key] = round(price, 2)
    return out


def fetch_date(target_date, api_key: str, base_url: str) -> list[dict]:
    """Every odds entry for a date, following pagination."""
    entries: list[dict] = []
    page = 1
    while True:
        response = requests.get(
            f"{base_url}/odds",
            headers={"x-apisports-key": api_key},
            params={"date": target_date.isoformat(), "page": page},
            timeout=40,
        )
        response.raise_for_status()
        payload = response.json()
        errors = payload.get("errors")
        if errors:
            if isinstance(errors, dict) and "plan" in errors:
                logger.warning("%s: %s", target_date, errors["plan"])
                return entries
            raise SystemExit(f"API-Football odds error for {target_date}: {errors}")

        entries.extend(payload.get("response") or [])
        paging = payload.get("paging") or {}
        if page >= int(paging.get("total") or 1):
            return entries
        page += 1
        time.sleep(REQUEST_DELAY_SECONDS)


class RateLimited(Exception):
    """The per-minute request cap, not the daily quota — see `backfill_missing_odds`."""


def fetch_fixture(fixture_id: int, api_key: str, base_url: str, timeout: int = 40) -> dict | None:
    """A single fixture's odds entry, or None. Never paginated — see module docstring."""
    response = requests.get(
        f"{base_url}/odds",
        headers={"x-apisports-key": api_key},
        params={"fixture": fixture_id},
        timeout=timeout,
    )
    if response.status_code == 429:
        raise RateLimited(f"fixture {fixture_id}")
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        if isinstance(errors, dict) and "plan" in errors:
            logger.warning("fixture %s not available on this plan (%s)", fixture_id, errors["plan"])
            return None
        raise SystemExit(f"API-Football odds error for fixture {fixture_id}: {errors}")
    entries = payload.get("response") or []
    return entries[0] if entries else None


def apply_prices(session, match: Match, prices: dict) -> None:
    """Store a fixture's best prices, mirroring 1X2 into the legacy columns."""
    match.odds_markets = prices
    match.odds_updated_at = datetime.now(UTC).replace(tzinfo=None)
    winner = prices.get("match_winner") or {}
    if winner.get("home"):
        match.odds_home_win = winner["home"]
    if winner.get("draw"):
        match.odds_draw = winner["draw"]
    if winner.get("away"):
        match.odds_away_win = winner["away"]


def backfill_missing_odds(
    session,
    settings,
    since: datetime,
    until: datetime,
    max_fixtures: int,
) -> int:
    """Per-fixture fallback for API-Football matches the bulk pass missed.

    Scoped to `external_id LIKE 'apif-%'` — CSV-sourced historical rows use a
    different id scheme entirely and were never candidates for a live odds
    lookup — and to matches still missing `odds_markets`, so a match already
    priced (by either pass) is never re-fetched.
    """
    candidates = (
        session.query(Match)
        .filter(
            Match.external_id.like("apif-%"),
            Match.match_date >= since,
            Match.match_date < until,
            Match.odds_markets.is_(None),
        )
        .order_by(Match.match_date.asc())
        .limit(max_fixtures)
        .all()
    )
    updated = 0
    for match in candidates:
        fixture_id = match.external_id.removeprefix("apif-")
        try:
            entry = fetch_fixture(
                fixture_id, settings.api_football_key, settings.api_football_base_url
            )
        except RateLimited:
            # The per-minute cap, not the daily quota — every fixture after
            # this one would fail the same way this run, so stop rather than
            # burn through the rest of `candidates` one 429 at a time. They
            # stay unpriced and are picked up again next scheduled run.
            logger.warning(
                "Rate limited after %d/%d backfill fixture(s); resuming next run",
                updated,
                len(candidates),
            )
            break
        time.sleep(BACKFILL_DELAY_SECONDS)
        if entry is None:
            continue
        prices = best_prices(entry)
        if not prices:
            continue
        apply_prices(session, match, prices)
        updated += 1
    if candidates:
        logger.info(
            "Backfill: priced %d of %d fixture(s) missed by the bulk pass", updated, len(candidates)
        )
    return updated


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fetch bookmaker odds for upcoming fixtures")
    parser.add_argument("--days", type=int, default=3, help="Days ahead, including today")
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=3,
        help="Days back to retry fixtures missed by the bulk pass",
    )
    parser.add_argument(
        "--max-backfill",
        type=int,
        default=40,
        help="Cap on per-fixture fallback requests, so a bad day can't exhaust the daily quota",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.api_football_key:
        raise SystemExit("API_FOOTBALL_KEY is not set. Add it to .env — see docs/setup_guide.md.")

    today = datetime.now(UTC).date()
    by_external: dict[str, dict] = {}
    for offset in range(args.days):
        target = today + timedelta(days=offset)
        entries = fetch_date(target, settings.api_football_key, settings.api_football_base_url)
        for entry in entries:
            fixture_id = (entry.get("fixture") or {}).get("id")
            if fixture_id is None:
                continue
            prices = best_prices(entry)
            if prices:
                by_external[f"apif-{fixture_id}"] = prices
        logger.info("%s: %d fixtures quoted", target, len(entries))
        time.sleep(REQUEST_DELAY_SECONDS)

    if not by_external:
        logger.warning("No odds returned for the requested dates.")

    session = SessionLocal()
    try:
        matches = session.query(Match).filter(Match.external_id.in_(list(by_external))).all()
        for match in matches:
            apply_prices(session, match, by_external[match.external_id])
        session.commit()
        logger.info(
            "Bulk pass: priced %d of %d quoted fixtures that are in our database "
            "(the rest are competitions this engine does not model).",
            len(matches),
            len(by_external),
        )

        since = datetime.combine(today - timedelta(days=args.backfill_days), datetime.min.time())
        until = datetime.combine(today + timedelta(days=args.days), datetime.min.time())
        backfill_missing_odds(session, settings, since, until, args.max_backfill)
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    main()
