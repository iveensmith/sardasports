"""Ingest upcoming football fixtures so the platform has something to predict.

Every match in this database is a *completed* one — the engine was built and
verified by predicting matches whose results are already known. That is the
right way to measure a model and the wrong way to run a product: a "Today's
Predictions" page reading from historical rows has nothing to show.

This fills that gap. It pulls scheduled fixtures from API-Football and
inserts them with `status="scheduled"` and no score, which is exactly the
shape `/fixtures/today` and `/predict/{match_id}` already expect. Nothing in
the prediction path changes.

**Only competitions the engine actually models are ingested.** API-Football
returns every fixture on earth for a given date — on a sampled day, 91
fixtures of which 3 were in a league this engine has trained on. Ingesting
the rest would manufacture a busy-looking board of predictions for teams
with no Elo history and no competition one-hot, i.e. two default 1500
ratings and a shrug rendered as a percentage. `LEAGUE_ID_TO_COMPETITION`
below is therefore an allowlist keyed on API-Football's stable league ids,
and it maps onto `ml.training.common.KNOWN_COMPETITIONS` exactly.

Quota: one request per date (not per fixture). The free plan serves the
`date` parameter — note it does *not* serve `next`, which is why this walks
explicit dates rather than asking for "the next N fixtures".

Usage:
    uv run python scripts/fetch_upcoming_fixtures.py            # today + 6 days
    uv run python scripts/fetch_upcoming_fixtures.py --days 3
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import UTC, datetime, timedelta

import requests

from app.database.session import SessionLocal
from app.models.match import Match
from app.services.team_identity import TeamResolver
from app.utils.config import get_settings
from app.utils.seasons import fallback_label, label_like
from app.utils.team_names import normalize_team_name
from ml.api_competitions import BY_ID
from ml.api_competitions import enabled as api_enabled

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REQUEST_DELAY_SECONDS = 1.0
SPORT = "football"

# Fixture statuses that mean "hasn't been played yet". Deliberately narrow:
# anything in progress or finished is left to the historical ingest path,
# which records real scores.
UPCOMING_STATUSES = {"NS", "TBD"}

# Youth and reserve sides are different entities from the senior teams this
# engine has history for. API-Football files youth internationals under the
# same "Friendlies" league id as senior ones, so without this filter a board
# of "England U17 vs Israel U17" arrives with two default 1500 ratings and no
# prior matches — a 50/50 dressed up as a prediction.
#
# The word boundaries are load-bearing: without them the `B` alternative
# matches the letter B anywhere and would exclude almost every club.
EXCLUDED_TEAM_PATTERN = re.compile(r"\b(U-?\d{2}|II|B|Reserves|Youth|Academy)\b", re.IGNORECASE)

# API-Football league id -> our competition name. Ids are stable; names are
# not (API-Football writes "Süper Lig", we write "Turkish Super Lig"), so the
# id is the join key. Every value here must exist in
# ml.training.common.KNOWN_COMPETITIONS — enforced by a test.
LEAGUE_ID_TO_COMPETITION = {
    **{c.api_id: c.name for c in api_enabled()},
    39: "English Premier League",
    40: "English Championship",
    41: "English League One",
    42: "English League Two",
    43: "English National League",
    140: "Spanish La Liga",
    141: "Spanish Segunda Division",
    78: "German Bundesliga",
    79: "German 2. Bundesliga",
    135: "Italian Serie A",
    136: "Italian Serie B",
    61: "French Ligue 1",
    62: "French Ligue 2",
    88: "Dutch Eredivisie",
    144: "Belgian Pro League",
    94: "Portuguese Primeira Liga",
    203: "Turkish Super Lig",
    197: "Greek Super League",
    179: "Scottish Premiership",
    253: "Major League Soccer",
    307: "Saudi Pro League",
    128: "Argentine Primera Division",
    71: "Brazilian Serie A",
    98: "Japanese J1 League",
    262: "Mexican Liga MX",
    235: "Russian Premier League",
    106: "Polish Ekstraklasa",
    103: "Norwegian Eliteserien",
    218: "Austrian Bundesliga",
    169: "Chinese Super League",
    119: "Danish Superliga",
    244: "Finnish Veikkausliiga",
    357: "Irish Premier Division",
    283: "Romanian Liga I",
    113: "Swedish Allsvenskan",
    207: "Swiss Super League",
    1: "FIFA World Cup",
    4: "UEFA European Championship",
    5: "UEFA Nations League",
    9: "Copa America",
    6: "Africa Cup of Nations",
    36: "Africa Cup of Nations Qualifiers",
    10: "International Friendlies",
}

# Competitions played on neutral ground — kept in step with
# scripts/clean_data.NEUTRAL_VENUE_COMPETITIONS.
NEUTRAL_VENUE_COMPETITIONS = {
    "FIFA World Cup",
    "UEFA European Championship",
    "Copa America",
    "Africa Cup of Nations",
}


def fetch_date(target_date, api_key: str, base_url: str, timeout: int = 40) -> list[dict]:
    """Every fixture API-Football lists for one date, unfiltered."""
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


def rows_from_fixtures(items: list[dict]) -> tuple[list[dict], int]:
    """Keep only upcoming fixtures in modelled competitions.

    Returns (rows, skipped_unmodelled) so the caller can report honestly how
    much of the day's card the engine actually covers.
    """
    rows, skipped = [], 0
    for item in items:
        fixture = item.get("fixture", {})
        if fixture.get("status", {}).get("short") not in UPCOMING_STATUSES:
            continue
        league_id = (item.get("league") or {}).get("id")
        competition = LEAGUE_ID_TO_COMPETITION.get(league_id)
        if competition is None:
            skipped += 1
            continue
        home_info = item.get("teams", {}).get("home") or {}
        away_info = item.get("teams", {}).get("away") or {}
        home, away = home_info.get("name"), away_info.get("name")
        date_raw = fixture.get("date")
        if not (home and away and date_raw):
            continue
        # A registry competition's reserve sides are real members: Bayern II
        # plays in the 3. Liga and Real Madrid Castilla in the Primera
        # Federación. The youth/reserve filter exists for the Friendlies feed,
        # which mixes U17 sides in with senior ones, and does not apply there.
        registered = BY_ID.get(league_id)
        # Friendlies-type feeds mix under-age sides in with senior ones, so they
        # keep the filter even when registered.
        if (registered is None or registered.exclude_youth) and (
            EXCLUDED_TEAM_PATTERN.search(home) or EXCLUDED_TEAM_PATTERN.search(away)
        ):
            skipped += 1
            continue
        kickoff = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
        league_info = item.get("league") or {}
        season_year = int(league_info.get("season") or kickoff.year)
        rows.append(
            {
                "external_id": f"apif-{fixture.get('id')}",
                "match_date": kickoff.astimezone(UTC).replace(tzinfo=None),
                "competition": competition,
                # Resolved in `load_rows`, where the competition's existing
                # history is available to match its label format.
                "season_year": season_year,
                "season": (
                    f"{season_year}-{season_year + 1}"
                    if registered and registered.split_year
                    else str(season_year) if registered else None
                ),
                "neutral_venue": (
                    registered.is_neutral(league_info.get("round"))
                    if registered
                    else competition in NEUTRAL_VENUE_COMPETITIONS
                ),
                "home_team": normalize_team_name(home),
                "away_team": normalize_team_name(away),
                "home_api_id": home_info.get("id"),
                "away_api_id": away_info.get("id"),
            }
        )
    return rows, skipped


def _season_label(session, row: dict, cache: dict) -> str:
    """The season label for a fixture, in the shape its competition already uses.

    A registry competition states its own calendar. For one loaded from
    Football-Data the answer is read off its newest stored season, so a live
    fixture lands in the same bucket as the rest of its league rather than in
    a "2026" beside a "2026-2027".
    """
    if row.get("season"):
        return row["season"]
    competition, year = row["competition"], row["season_year"]
    if competition not in cache:
        newest = (
            session.query(Match.season)
            .filter(Match.competition == competition, Match.season.isnot(None))
            .order_by(Match.match_date.desc())
            .first()
        )
        cache[competition] = newest[0] if newest else None
    sample = cache[competition]
    label = label_like(sample, year) if sample else None
    return label or fallback_label(year, row["match_date"].month)


def load_rows(session, rows: list[dict]) -> tuple[int, int]:
    """Insert new scheduled fixtures. Returns (inserted, already_present).

    Clubs are resolved by API id first, then name — the same resolver the
    historical ingest uses — so a club has one identity whichever way it
    arrives. Matching on name alone created a fresh default-rated club for any
    API spelling that differed from Football-Data's, which then got a
    coin-flip prediction.
    """
    existing = {
        e for (e,) in session.query(Match.external_id).filter(Match.external_id.isnot(None)).all()
    }
    resolver = TeamResolver(session)
    label_cache: dict = {}
    inserted = skipped = 0
    for row in rows:
        if row["external_id"] in existing:
            skipped += 1
            continue
        home = resolver.resolve(row["home_team"], row.get("home_api_id"), row["competition"])
        away = resolver.resolve(row["away_team"], row.get("away_api_id"), row["competition"])
        session.add(
            Match(
                external_id=row["external_id"],
                sport=SPORT,
                match_date=row["match_date"],
                competition=row["competition"],
                season=_season_label(session, row, label_cache),
                neutral_venue=row["neutral_venue"],
                home_team_id=home.id,
                away_team_id=away.id,
                # No score: this hasn't been played. `is_completed` stays
                # False and the match never enters training or Elo.
                home_score=None,
                away_score=None,
                status="scheduled",
            )
        )
        existing.add(row["external_id"])
        inserted += 1
    session.flush()
    if resolver.created:
        # A created club starts at the default rating, so its fixtures are
        # coin-flip predictions. Most of the time it is an existing club under a
        # different spelling that has not been mapped to its API id yet — say so,
        # by name, rather than let it pass as a new club.
        logger.warning(
            "Created %d club(s) that matched nothing already held: %s. Each starts at the "
            "default rating; if one is an existing club under another spelling, map it with "
            "`scripts/fetch_api_competitions.py --map-teams --ids <league id>` or merge it.",
            len(resolver.created),
            ", ".join(f"{name} (api {api_id})" for name, api_id, _ in resolver.created),
        )
    return inserted, skipped


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ingest upcoming fixtures for modelled leagues")
    parser.add_argument("--days", type=int, default=7, help="Days ahead to fetch, including today")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.api_football_key:
        raise SystemExit("API_FOOTBALL_KEY is not set. Add it to .env — see docs/setup_guide.md.")

    today = datetime.now(UTC).date()
    all_rows: list[dict] = []
    total_listed = total_unmodelled = 0

    for offset in range(args.days):
        target = today + timedelta(days=offset)
        items = fetch_date(target, settings.api_football_key, settings.api_football_base_url)
        rows, unmodelled = rows_from_fixtures(items)
        total_listed += len(items)
        total_unmodelled += unmodelled
        logger.info(
            "%s: %d fixtures listed, %d upcoming in modelled competitions",
            target,
            len(items),
            len(rows),
        )
        all_rows.extend(rows)
        time.sleep(REQUEST_DELAY_SECONDS)

    if not all_rows:
        logger.warning(
            "No upcoming fixtures in modelled competitions over the next %d day(s). "
            "%d fixtures were listed but belong to competitions this engine has no "
            "model for — see LEAGUE_ID_TO_COMPETITION.",
            args.days,
            total_unmodelled,
        )
        return

    session = SessionLocal()
    try:
        inserted, already = load_rows(session, all_rows)
        session.commit()
    finally:
        session.close()

    logger.info(
        "Inserted %d upcoming fixtures (%d already present). "
        "Of %d fixtures listed across %d day(s), %d were in competitions this engine "
        "does not model and were deliberately skipped.",
        inserted,
        already,
        total_listed,
        args.days,
        total_unmodelled,
    )


if __name__ == "__main__":
    main()
