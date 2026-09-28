"""Sync real injury/suspension data from API-Football (api-sports.io) for teams
already in our database.

Requires `API_FOOTBALL_KEY` in `.env` — sign up at
https://dashboard.api-football.com/register to get one (a free tier exists
with a low daily request quota; check `coverage.injuries` on that league's
`/leagues` response before relying on this for a league, since not every
league/season has injury coverage).

Live-verified against a real key: `team`+`season` returns one entry per
*fixture* a player missed, not one entry per player — a long-term injury
spanning a whole season shows up a dozen-plus times. There's also no
resolved/recovered flag anywhere in the response. To turn that into a
useful "current status" list, `sync_team_injuries` keeps only each player's
single most-recent-dated entry — the best available proxy for "still out,"
though a player who fully recovered with no newer fixture entry yet will
still show their last injury until the next one supersedes it. This
dedup logic, and the season auto-detection below, were added after finding
both issues against live data, not assumed upfront.

Usage:
    uv run python scripts/sync_injuries.py --team Arsenal
    uv run python scripts/sync_injuries.py --league "English Premier League"
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, datetime

import requests

from app.database.session import SessionLocal
from app.models import Injury, Team
from app.utils.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REQUEST_DELAY_SECONDS = 1.0  # be polite to the free-tier rate limit


class ApiFootballError(Exception):
    pass


def _headers(api_key: str) -> dict:
    return {"x-apisports-key": api_key}


def current_api_football_season(today: datetime | None = None) -> int:
    """API-Football's `season` param is the year a European season *starts*
    (season=2025 -> the 2025-26 season). European seasons run roughly
    August-May, so before July we're still in the season that started the
    previous calendar year."""
    today = today or datetime.now(UTC)
    return today.year if today.month >= 7 else today.year - 1


def _keep_latest_entry_per_player(entries: list[dict]) -> list[dict]:
    """Collapse "one row per missed fixture" down to "one row per player,"
    keeping the most recent fixture_date as the best-available proxy for
    current status (see module docstring for why there's no better signal)."""
    latest: dict[str, dict] = {}
    for entry in entries:
        name = entry["player_name"]
        existing = latest.get(name)
        if existing is None:
            latest[name] = entry
            continue
        existing_date, new_date = existing["fixture_date"], entry["fixture_date"]
        if new_date is not None and (existing_date is None or new_date > existing_date):
            latest[name] = entry
    return list(latest.values())


def resolve_api_football_team_id(session, team: Team, settings) -> int | None:
    """Resolve and cache `team.api_football_id` by searching API-Football by name."""
    if team.api_football_id is not None:
        return team.api_football_id

    if not settings.api_football_key:
        raise ApiFootballError("API_FOOTBALL_KEY is not set")

    response = requests.get(
        f"{settings.api_football_base_url}/teams",
        headers=_headers(settings.api_football_key),
        params={"search": team.name},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()

    results = payload.get("response", [])
    if not results:
        logger.warning("No API-Football team found matching '%s'", team.name)
        return None

    # `search` can return multiple loosely-matching teams (youth/reserve
    # sides, similarly-named clubs); take the first result, which the API
    # ranks by relevance, and log if there's ambiguity worth a human check.
    if len(results) > 1:
        logger.info(
            "'%s' matched %d API-Football teams, using the first: %s",
            team.name,
            len(results),
            [r.get("team", {}).get("name") for r in results],
        )

    team_id = results[0].get("team", {}).get("id")
    if team_id is None:
        raise ApiFootballError(f"Unexpected /teams response shape for '{team.name}': {payload}")

    team.api_football_id = team_id
    session.flush()
    return team_id


def _parse_injury_entry(entry: dict) -> dict | None:
    """Defensive parse: returns None (and logs) rather than raising on an
    unexpected shape, so one malformed entry doesn't abort the whole sync.

    Verified against a live API-Football response: entries with a null
    `player.name` do occur in practice (sparse data for some records), so
    this checks the *value*, not just key presence — `.get("name")` alone
    doesn't catch a present-but-null field.
    """
    try:
        player = entry["player"]
        player_name = player.get("name")
        if not player_name:
            logger.warning("Skipping injury entry with no player name: %s", entry)
            return None

        fixture = entry.get("fixture") or {}
        return {
            "player_name": player_name,
            "injury_type": player.get("type"),
            "reason": player.get("reason"),
            "fixture_external_id": fixture.get("id"),
            "fixture_date": _parse_iso_datetime(fixture.get("date")),
        }
    except (KeyError, TypeError) as exc:
        logger.warning("Skipping unparseable injury entry %s: %s", entry, exc)
        return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def sync_team_injuries(session, team: Team, settings) -> int:
    """Fetch current injuries for one team and replace its stored rows.
    Returns the number of injury rows stored (0 is a valid, real result)."""
    if not settings.api_football_key:
        raise ApiFootballError("API_FOOTBALL_KEY is not set")

    api_team_id = resolve_api_football_team_id(session, team, settings)
    if api_team_id is None:
        return 0

    season = settings.api_football_season or current_api_football_season()
    response = requests.get(
        f"{settings.api_football_base_url}/injuries",
        headers=_headers(settings.api_football_key),
        params={"team": api_team_id, "season": season},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()

    if payload.get("errors"):
        raise ApiFootballError(
            f"API-Football returned errors for '{team.name}': {payload['errors']}"
        )

    entries = [_parse_injury_entry(e) for e in payload.get("response", [])]
    entries = [e for e in entries if e is not None]
    entries = _keep_latest_entry_per_player(entries)

    session.query(Injury).filter(Injury.team_id == team.id).delete()
    for entry in entries:
        session.add(Injury(team_id=team.id, source="api-football", **entry))

    team.injuries_synced_at = datetime.now(UTC).replace(tzinfo=None)
    session.commit()
    logger.info("Synced %d injury entries for %s", len(entries), team.name)
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync injuries from API-Football")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--team", help="Sync a single team by name")
    group.add_argument("--league", help="Sync every team in this competition already in the DB")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.api_football_key:
        raise SystemExit(
            "API_FOOTBALL_KEY is not set. Sign up at "
            "https://dashboard.api-football.com/register and add it to .env."
        )

    session = SessionLocal()
    try:
        if args.team:
            team = session.query(Team).filter(Team.name == args.team).one_or_none()
            if team is None:
                raise SystemExit(f"No team named '{args.team}' in the database.")
            sync_team_injuries(session, team, settings)
        else:
            teams = session.query(Team).filter(Team.league == args.league).all()
            if not teams:
                raise SystemExit(f"No teams found for competition '{args.league}'.")
            for i, team in enumerate(teams):
                try:
                    sync_team_injuries(session, team, settings)
                except ApiFootballError as exc:
                    logger.warning("Skipping %s: %s", team.name, exc)
                if i < len(teams) - 1:
                    time.sleep(REQUEST_DELAY_SECONDS)
    finally:
        session.close()


if __name__ == "__main__":
    main()
