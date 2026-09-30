"""Fetch per-fixture statistics and goal events for completed matches.

`fetch_results.py` fetches only the score for a fixture it closes out,
flagging statistics as "a deliberate follow-up, not an oversight" — this is
that follow-up. Two more requests per fixture, at API-Football's
`/fixtures/statistics` and `/fixtures/events`, filling in:

- Shots, shots on target, corners, yellow/red cards — columns that already
  existed for the historical Football-Data.co.uk training data but were
  never live-fetched for a match this engine had actually predicted.
- Possession, offsides, fouls — new columns (see the
  `b7c8d9e0f1a2_match_statistics_and_events` migration). The historical
  training data never had these either, so there is no trained model for
  them and none of this is used as a training feature; it exists to answer
  "what actually happened", not to predict it.
- `match_events` — the goals themselves, in order, with a running score.
  Football only, and only ever the shape API-Football actually reports; no
  event is invented for a fixture the source has nothing for.

**Scoped by `stats_fetched_at`, not by whether a stat column is empty.**
Several competitions genuinely report none of this even when the fixture
itself is real and finished, and an empty response has to be
distinguishable from "never asked" or every scheduled run would re-request
the same uncovered fixtures forever.

**Team assignment is by name, not by a stored API-Football team id.** This
engine matches teams across sources by name already (see
`app/utils/team_names.py`); reusing `fold_team_key` for the statistics and
events responses avoids a third request per fixture just to learn which
side is home.

Usage:
    uv run python scripts/fetch_match_stats.py                    # up to 40 fixtures
    uv run python scripts/fetch_match_stats.py --max-fixtures 100
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, datetime

import requests

from app.database.session import SessionLocal
from app.models.match import Match
from app.models.match_event import MatchEvent
from app.utils.config import get_settings
from app.utils.team_names import fold_team_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REQUEST_DELAY_SECONDS = 1.0

# API-Football's `/fixtures/statistics` "type" strings, verbatim, mapped to
# the (home_attr, away_attr) pair on Match they fill. Other real fields the
# endpoint reports (Blocked Shots, Shots insidebox/outsidebox, Goalkeeper
# Saves, passes) have no column here and are left alone rather than growing
# the schema for stats nothing reads yet.
STAT_FIELDS: dict[str, tuple[str, str]] = {
    "Total Shots": ("home_shots", "away_shots"),
    "Shots on Goal": ("home_shots_on_target", "away_shots_on_target"),
    "Corner Kicks": ("home_corners", "away_corners"),
    "Yellow Cards": ("home_yellow_cards", "away_yellow_cards"),
    "Red Cards": ("home_red_cards", "away_red_cards"),
    "Fouls": ("home_fouls", "away_fouls"),
    "Offsides": ("home_offsides", "away_offsides"),
    "Ball Possession": ("home_possession", "away_possession"),
}


class RateLimited(Exception):
    """The per-minute request cap, not the daily quota — see `backfill_match_stats`."""


def _parse_stat_value(raw: object) -> int | None:
    """API-Football reports possession as `"55%"` and a stat the competition
    doesn't track as `None` — both need to become a plain int or nothing."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.rstrip("%").strip()
        if raw == "":
            return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def fetch_statistics(fixture_id: str, api_key: str, base_url: str, timeout: int = 40) -> list[dict]:
    """Both teams' statistics for one fixture, or an empty list."""
    response = requests.get(
        f"{base_url}/fixtures/statistics",
        headers={"x-apisports-key": api_key},
        params={"fixture": fixture_id},
        timeout=timeout,
    )
    if response.status_code == 429:
        raise RateLimited(f"fixture {fixture_id} statistics")
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        if isinstance(errors, dict) and "plan" in errors:
            logger.warning(
                "fixture %s statistics not available on this plan (%s)", fixture_id, errors["plan"]
            )
            return []
        raise SystemExit(f"API-Football statistics error for fixture {fixture_id}: {errors}")
    return payload.get("response") or []


def fetch_events(fixture_id: str, api_key: str, base_url: str, timeout: int = 40) -> list[dict]:
    """Every event API-Football has for one fixture, unfiltered."""
    response = requests.get(
        f"{base_url}/fixtures/events",
        headers={"x-apisports-key": api_key},
        params={"fixture": fixture_id},
        timeout=timeout,
    )
    if response.status_code == 429:
        raise RateLimited(f"fixture {fixture_id} events")
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        if isinstance(errors, dict) and "plan" in errors:
            logger.warning(
                "fixture %s events not available on this plan (%s)", fixture_id, errors["plan"]
            )
            return []
        raise SystemExit(f"API-Football events error for fixture {fixture_id}: {errors}")
    return payload.get("response") or []


def _side_for(team_name: str, match: Match) -> str | None:
    """Which side of `match` this API-Football team block belongs to, by
    name — see the module docstring for why this beats a stored id."""
    key = fold_team_key(team_name)
    if key == fold_team_key(match.home_team.name):
        return "home"
    if key == fold_team_key(match.away_team.name):
        return "away"
    return None


def apply_statistics(match: Match, blocks: list[dict]) -> bool:
    """Fill in whichever `STAT_FIELDS` this fixture's response actually
    carries. Returns whether anything was set, purely for logging — the
    fixture counts as "fetched" either way (see `backfill_match_stats`)."""
    changed = False
    for block in blocks:
        team = block.get("team") or {}
        side = _side_for(team.get("name", ""), match)
        if side is None:
            continue
        for stat in block.get("statistics") or []:
            field_pair = STAT_FIELDS.get(stat.get("type"))
            if field_pair is None:
                continue
            value = _parse_stat_value(stat.get("value"))
            if value is None:
                continue
            setattr(match, field_pair[0] if side == "home" else field_pair[1], value)
            changed = True
    return changed


def events_for_match(match: Match, items: list[dict]) -> list[MatchEvent]:
    """The goals in `items`, in order, each carrying the running score.

    Only `type == "Goal"` — cards, substitutions and VAR reviews are real
    events too but this engine only shows the scoring timeline for now. A
    missed penalty is reported as a "Goal"-type event with that detail and
    is explicitly excluded: no goal was scored.
    """
    events: list[MatchEvent] = []
    home_score = away_score = 0
    for item in items:
        if (item.get("type") or "").lower() != "goal":
            continue
        detail = item.get("detail") or "Goal"
        if detail.lower() == "missed penalty":
            continue
        team = item.get("team") or {}
        side = _side_for(team.get("name", ""), match)
        if side is None:
            continue
        player = (item.get("player") or {}).get("name")
        if not player:
            continue
        if side == "home":
            home_score += 1
        else:
            away_score += 1
        time_block = item.get("time") or {}
        events.append(
            MatchEvent(
                match_id=match.id,
                minute=time_block.get("elapsed") or 0,
                added_time=time_block.get("extra"),
                side=side,
                player=player,
                assist=(item.get("assist") or {}).get("name"),
                detail=detail,
                home_score_after=home_score,
                away_score_after=away_score,
            )
        )
    if events and match.home_score is not None and (home_score, away_score) != (
        match.home_score,
        match.away_score,
    ):
        # The two sources disagreeing is a real data problem worth knowing
        # about, not a reason to drop the timeline — the events are still
        # genuinely what API-Football reported.
        logger.warning(
            "fixture for match %d: events tally %d-%d does not match stored score %d-%d",
            match.id,
            home_score,
            away_score,
            match.home_score,
            match.away_score,
        )
    return events


def backfill_match_stats(session, settings, max_fixtures: int) -> int:
    """Per-fixture statistics + events for completed matches that have never
    been asked for them (`stats_fetched_at is null`).

    Football only, and scoped to `external_id LIKE 'apif-%'` the same way
    `fetch_odds.py`'s backfill is — CSV-sourced historical rows were never
    candidates for a live per-fixture lookup.
    """
    candidates = (
        session.query(Match)
        .filter(
            Match.external_id.like("apif-%"),
            Match.sport == "football",
            Match.status == "completed",
            Match.stats_fetched_at.is_(None),
        )
        .order_by(Match.match_date.desc())
        .limit(max_fixtures)
        .all()
    )
    updated = 0
    for match in candidates:
        fixture_id = match.external_id.removeprefix("apif-")
        try:
            stat_blocks = fetch_statistics(
                fixture_id, settings.api_football_key, settings.api_football_base_url
            )
            time.sleep(REQUEST_DELAY_SECONDS)
            event_items = fetch_events(
                fixture_id, settings.api_football_key, settings.api_football_base_url
            )
        except RateLimited:
            # The per-minute cap, not the daily quota — every fixture after
            # this one would fail the same way this run, so stop rather than
            # burn through the rest of `candidates` one 429 at a time. They
            # stay unmarked and are picked up again next scheduled run.
            logger.warning(
                "Rate limited after %d/%d fixture(s); resuming next run", updated, len(candidates)
            )
            break
        time.sleep(REQUEST_DELAY_SECONDS)

        got_stats = apply_statistics(match, stat_blocks) if stat_blocks else False
        events = events_for_match(match, event_items) if event_items else []
        if events:
            session.add_all(events)
        match.stats_fetched_at = datetime.now(UTC).replace(tzinfo=None)
        if got_stats or events:
            updated += 1

    if candidates:
        logger.info(
            "Fetched statistics/events for %d/%d completed fixture(s)", updated, len(candidates)
        )
    return updated


def fetch_and_apply_match_stats(max_fixtures: int = 40) -> int:
    """The core entry point — `main()` is a thin CLI wrapper, and
    `app.scheduler` calls this directly, the same separation
    `fetch_and_apply_results` uses."""
    settings = get_settings()
    if not settings.api_football_key:
        raise SystemExit("API_FOOTBALL_KEY is not set. Add it to .env — see docs/setup_guide.md.")

    session = SessionLocal()
    try:
        updated = backfill_match_stats(session, settings, max_fixtures)
        session.commit()
    finally:
        session.close()
    return updated


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Fetch per-fixture statistics and goal events for completed matches"
    )
    parser.add_argument(
        "--max-fixtures",
        type=int,
        default=40,
        help="Cap on fixtures to fetch this run (two requests each)",
    )
    args = parser.parse_args(argv)
    fetch_and_apply_match_stats(max_fixtures=args.max_fixtures)


if __name__ == "__main__":
    main()
