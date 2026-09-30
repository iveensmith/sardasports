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
from app.models.team import Team
from app.utils.config import get_settings
from app.utils.team_names import fold_team_key, normalize_team_name

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
    39: "English Premier League",
    40: "English Championship",
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
        home = (item.get("teams", {}).get("home") or {}).get("name")
        away = (item.get("teams", {}).get("away") or {}).get("name")
        date_raw = fixture.get("date")
        if not (home and away and date_raw):
            continue
        if EXCLUDED_TEAM_PATTERN.search(home) or EXCLUDED_TEAM_PATTERN.search(away):
            skipped += 1
            continue
        kickoff = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
        rows.append(
            {
                "external_id": f"apif-{fixture.get('id')}",
                "match_date": kickoff.astimezone(UTC).replace(tzinfo=None),
                "competition": competition,
                "season": str((item.get("league") or {}).get("season") or kickoff.year),
                "neutral_venue": competition in NEUTRAL_VENUE_COMPETITIONS,
                "home_team": normalize_team_name(home),
                "away_team": normalize_team_name(away),
            }
        )
    return rows, skipped


def _get_or_create_team(session, cache: dict, name: str, league: str) -> Team:
    key = (SPORT, name)
    if key in cache:
        return cache[key]
    team = session.query(Team).filter(Team.sport == SPORT, Team.name == name).one_or_none()
    if team is None:
        # Accent/punctuation-folded fallback before creating anything new:
        # sources disagree on diacritics for the same club ("Castellon" from
        # Football-Data.co.uk, "Castellón" from API-Football), and a second
        # row splits that club's history and leaves the new one with no Elo,
        # so a real fixture gets a default-rated coin-flip prediction.
        # Folding affects matching only; the stored name is untouched.
        folded = fold_team_key(name)
        for candidate in session.query(Team).filter(Team.sport == SPORT).all():
            if fold_team_key(candidate.name) == folded:
                cache[key] = candidate
                return candidate

        team = Team(name=name, league=league, sport=SPORT)
        session.add(team)
        session.flush()
    cache[key] = team
    return team


def load_rows(session, rows: list[dict]) -> tuple[int, int]:
    """Insert new scheduled fixtures. Returns (inserted, already_present)."""
    existing = {
        e for (e,) in session.query(Match.external_id).filter(Match.external_id.isnot(None)).all()
    }
    cache: dict = {}
    inserted = skipped = 0
    for row in rows:
        if row["external_id"] in existing:
            skipped += 1
            continue
        home = _get_or_create_team(session, cache, row["home_team"], row["competition"])
        away = _get_or_create_team(session, cache, row["away_team"], row["competition"])
        session.add(
            Match(
                external_id=row["external_id"],
                sport=SPORT,
                match_date=row["match_date"],
                competition=row["competition"],
                season=row["season"],
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
