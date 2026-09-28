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

Quota: one request per page per date, not per fixture.

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch bookmaker odds for upcoming fixtures")
    parser.add_argument("--days", type=int, default=3, help="Days ahead, including today")
    args = parser.parse_args()

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
        return

    session = SessionLocal()
    updated = 0
    try:
        matches = session.query(Match).filter(Match.external_id.in_(list(by_external))).all()
        now = datetime.now(UTC).replace(tzinfo=None)
        for match in matches:
            prices = by_external[match.external_id]
            match.odds_markets = prices
            match.odds_updated_at = now
            # Mirror the 1X2 prices into the existing columns so value
            # detection and the ROI backtest keep working unchanged.
            winner = prices.get("match_winner") or {}
            if winner.get("home"):
                match.odds_home_win = winner["home"]
            if winner.get("draw"):
                match.odds_draw = winner["draw"]
            if winner.get("away"):
                match.odds_away_win = winner["away"]
            updated += 1
        session.commit()
    finally:
        session.close()

    logger.info(
        "Priced %d of %d quoted fixtures that are in our database "
        "(the rest are competitions this engine does not model).",
        updated,
        len(by_external),
    )


if __name__ == "__main__":
    main()
