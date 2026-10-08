"""Tennis fixtures and fresh results, from ESPN's public scoreboard.

tennis-data.co.uk (see `scripts/fetch_tennis.py`) is the source of the historical
record, with bookmaker odds and the set-by-set scores the total-games model needs, but
it publishes results only: no schedule, and a few days of lag. This fills both gaps for
the tournaments being played right now.

The source is ESPN's public scoreboard JSON (`site.api.espn.com`). It is not a licensed
data product: it is the feed ESPN's own pages use, available without a key, and it can
change or disappear without notice. That is why every call here is wrapped so a failure
leaves the existing data alone, why the source is one small module that can be replaced
by a licensed feed, and why the pages say where the data comes from. It covers the ATP
and WTA tours (qualifying included). It does not cover Challenger or ITF events.

How a match is stored:

* Singles only. Doubles are a different sport as far as the ratings are concerned.
* The two players go into the home and away slots by a hash of the match, not by ESPN's
  order, exactly as `fetch_tennis` does, so that slot position carries no information.
* A match is a result only when it was played to a finish. A retirement, a walkover or a
  cancelled match is left out, as `fetch_tennis` leaves them out, because a half-played
  scoreline would teach the totals model something false.
* If tennis-data later publishes the same match, its row takes over the ESPN one in
  place (see `fetch_tennis.load_rows`), so nothing is counted twice and anything stored
  against the match keeps pointing at it.

Names. ESPN gives "Carlos Alcaraz"; the history stores "Alcaraz C.". Each name is
matched to an existing player by surname and first initial, and a player the history
has never seen is created in the same "Surname I." form.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import requests
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.team import Team

logger = logging.getLogger(__name__)

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis"
SPORT = "tennis"
ESPN_PREFIX = "espn-tennis-"
TOURS = {"atp": "ATP", "wta": "WTA"}
USER_AGENT = "Mozilla/5.0 (compatible; SARDASPORTS data refresh)"
TOURNAMENTS_PATH = Path(__file__).resolve().parent.parent.parent / "ml" / "tennis_tournaments.json"

# How far apart two dates can be and still be the same match, to cover the two sources
# disagreeing about a day (time zones, a match played past midnight).
SAME_MATCH_DAYS = 4

_STOP = {
    "open", "masters", "tennis", "international", "championships", "championship", "classic",
    "cup", "atp", "wta", "presented", "by", "the", "of", "and", "de", "du", "la", "el", "women",
    "womens", "mens", "men", "tour", "series", "grand", "prix", "trophy", "challenge",
}  # fmt: skip


def _ascii(text: str) -> str:
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )


def _letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", _ascii(text))


@lru_cache(maxsize=1)
def _tournaments() -> list[tuple[frozenset, str, str, str]]:
    """(name tokens, location, surface, name) for each tournament in the history."""
    if not TOURNAMENTS_PATH.exists():
        return []
    raw = json.loads(TOURNAMENTS_PATH.read_text(encoding="utf-8"))
    out = []
    for name, info in raw.items():
        tokens = frozenset(t for t in re.findall(r"[a-z]+", _ascii(name)) if t not in _STOP)
        out.append((tokens, _letters(info.get("location") or ""), info["surface"], name))
    return out


def surface_for(event_name: str, venue: str | None) -> tuple[str | None, str | None]:
    """(playing surface, the history's name for the tournament) for an ESPN event.

    Both are None when the tournament is not recognised, which the prediction handles by
    using the overall rating instead of a surface one, rather than guessing a surface.
    The history's own tournament name is returned so that one tournament is always one
    group on a day's board, whichever source a match came from.
    """
    tokens = frozenset(t for t in re.findall(r"[a-z]+", _ascii(event_name)) if t not in _STOP)
    city = _letters((venue or "").split(",")[0])
    best: tuple[float, str, str] | None = None
    for known, location, surface, name in _tournaments():
        if tokens and known and tokens == known:
            return surface, name
        overlap = len(tokens & known) / max(1, len(tokens | known))
        if overlap >= 0.5 and (best is None or overlap > best[0]):
            best = (overlap, surface, name)
        if city and location and city == location and best is None:
            best = (0.4, surface, name)
    return (best[1], best[2]) if best else (None, None)


# --- players ---------------------------------------------------------------------


class PlayerIndex:
    """Finds the stored player for an ESPN name, creating one only if there is none."""

    def __init__(self, session: Session):
        self.session = session
        self.by_key: dict[tuple[str, str], Team] = {}
        for team in session.query(Team).filter(Team.sport == SPORT).all():
            body = team.name.rsplit(" ", 1)
            if len(body) == 2 and re.fullmatch(r"[A-Za-z]\.?", body[1]):
                self.by_key.setdefault((_letters(body[0]), body[1][0].lower()), team)

    def resolve(self, full_name: str, tour: str) -> Team:
        tokens = [t for t in re.split(r"\s+", full_name.strip()) if t]
        splits = []
        for k in range(1, len(tokens)):
            splits.append((tokens[k:], tokens[:k]))  # "Alex de Minaur": surname last
            splits.append((tokens[:k], tokens[k:]))  # "Te Rigele": surname first
        for surname, given in splits:
            key = (_letters(" ".join(surname)), _letters(given[0])[:1])
            if key in self.by_key:
                return self.by_key[key]
        surname, given = (tokens[1:], tokens[:1]) if len(tokens) > 1 else (tokens, [""])
        name = f"{' '.join(surname)} {given[0][:1].upper()}.".strip()
        team = self.session.query(Team).filter(Team.sport == SPORT, Team.name == name).one_or_none()
        if team is None:
            team = Team(name=name, league=tour, sport=SPORT)
            self.session.add(team)
            self.session.flush()
        self.by_key[(_letters(" ".join(surname)), _letters(given[0])[:1])] = team
        return team


# --- ESPN ---------------------------------------------------------------------------


def fetch_scoreboard(tour: str, day: str | None = None, timeout: int = 30) -> dict:
    params = {"dates": day} if day else {}
    response = requests.get(
        f"{BASE_URL}/{tour}/scoreboard",
        params=params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _slot_swap(competition_id: str) -> bool:
    return hashlib.sha256(f"espn|{competition_id}".encode()).digest()[0] % 2 == 1


def _sets_and_games(competitor: dict) -> tuple[int, int]:
    lines = competitor.get("linescores") or []
    sets = sum(1 for line in lines if line.get("winner"))
    games = sum(int(line.get("value") or 0) for line in lines)
    return sets, games


def parse_scoreboard(payload: dict, default_tour: str) -> list[dict]:
    """Singles matches in a scoreboard, as plain dicts ready for `upsert`."""
    rows = []
    for event in payload.get("events") or []:
        event_name = event.get("name") or ""
        major = bool(event.get("major"))
        venue = ((event.get("venue") or {}).get("displayName")) or None
        surface, tournament = surface_for(event_name, venue)
        tournament = tournament or event_name
        for grouping in event.get("groupings") or []:
            slug = (grouping.get("grouping") or {}).get("slug") or ""
            if "singles" not in slug or "doubles" in slug:
                continue
            tour = (
                "ATP" if slug.startswith("mens") else "WTA" if slug.startswith("womens") else None
            )
            tour = tour or default_tour
            for comp in grouping.get("competitions") or []:
                row = _parse_competition(comp, tour, major, surface, tournament)
                if row:
                    rows.append(row)
    return rows


def _parse_competition(
    comp: dict, tour: str, major: bool, surface: str | None, event_name: str
) -> dict | None:
    status = ((comp.get("status") or {}).get("type") or {}).get("name") or ""
    competitors = comp.get("competitors") or []
    if len(competitors) != 2 or not all(
        (c.get("athlete") or {}).get("fullName") for c in competitors
    ):
        return None  # a bye or an undecided slot
    if status in ("STATUS_SCHEDULED", "STATUS_IN_PROGRESS", "STATUS_DELAYED"):
        outcome = "scheduled"
    elif status == "STATUS_FINAL":
        outcome = "completed"
    else:
        return None  # retired, walkover, cancelled, suspended: no real result
    raw_date = comp.get("date") or comp.get("startDate")
    if not raw_date or not comp.get("id"):
        return None

    best_of = 5 if (major and tour == "ATP") else 3
    names = [c["athlete"]["fullName"] for c in competitors]
    row = {
        "external_id": f"{ESPN_PREFIX}{comp['id']}",
        "match_date": datetime.fromisoformat(raw_date.replace("Z", "+00:00")).replace(tzinfo=None),
        "competition": tour,
        "season": str(datetime.fromisoformat(raw_date.replace("Z", "+00:00")).year),
        "surface": surface,
        "best_of": best_of,
        "names": names,
        "status": outcome,
        "tournament": event_name,
        "sets": None,
        "games": None,
    }
    if outcome == "completed":
        a_sets, a_games = _sets_and_games(competitors[0])
        b_sets, b_games = _sets_and_games(competitors[1])
        needed = best_of // 2 + 1
        if max(a_sets, b_sets) != needed or a_sets == b_sets:
            return None  # not played to a finish
        row["sets"] = (a_sets, b_sets)
        row["games"] = (a_games, b_games)
    return row


# --- storing -----------------------------------------------------------------------


def _same_match(
    session: Session, a_id: int, b_id: int, when: datetime, exclude: str
) -> Match | None:
    window = timedelta(days=SAME_MATCH_DAYS)
    return (
        session.query(Match)
        .filter(
            Match.sport == SPORT,
            Match.match_date >= when - window,
            Match.match_date <= when + window,
            or_(
                (Match.home_team_id == a_id) & (Match.away_team_id == b_id),
                (Match.home_team_id == b_id) & (Match.away_team_id == a_id),
            ),
            Match.external_id != exclude,
        )
        .order_by(Match.match_date.desc())
        .first()
    )


def upsert(session: Session, rows: list[dict]) -> dict:
    players = PlayerIndex(session)
    counts = {"inserted": 0, "completed": 0, "skipped_duplicate": 0}
    for row in rows:
        a = players.resolve(row["names"][0], row["competition"])
        b = players.resolve(row["names"][1], row["competition"])
        if a.id == b.id:
            continue
        existing = (
            session.query(Match).filter(Match.external_id == row["external_id"]).one_or_none()
        )
        if existing is None:
            other = _same_match(session, a.id, b.id, row["match_date"], row["external_id"])
            # Already held, from tennis-data or under another ESPN id for the same fixture.
            if other is not None and (other.status == "completed" or row["status"] == "scheduled"):
                counts["skipped_duplicate"] += 1
                continue

        swap = _slot_swap(row["external_id"])
        home, away = (b, a) if swap else (a, b)
        sets = row["sets"]
        games = row["games"]
        if sets and swap:
            sets, games = (sets[1], sets[0]), (games[1], games[0])

        if existing is None:
            session.add(
                Match(
                    external_id=row["external_id"],
                    sport=SPORT,
                    match_date=row["match_date"],
                    competition=row["competition"],
                    season=row["season"],
                    surface=row["surface"],
                    best_of=row["best_of"],
                    tournament=row["tournament"],
                    neutral_venue=True,
                    home_team_id=home.id,
                    away_team_id=away.id,
                    home_score=None if not sets else sets[0],
                    away_score=None if not sets else sets[1],
                    home_games=None if not games else games[0],
                    away_games=None if not games else games[1],
                    status=row["status"],
                )
            )
            counts["inserted"] += 1
            continue

        existing.tournament = existing.tournament or row["tournament"]
        if existing.status == "completed":
            continue
        existing.match_date = row["match_date"]
        if row["surface"] and not existing.surface:
            existing.surface = row["surface"]
        if row["status"] == "completed" and sets:
            # Keep the stored orientation: map the result onto whichever slot each player holds.
            a_sets, b_sets = row["sets"]
            a_games, b_games = row["games"]
            if existing.home_team_id == a.id:
                existing.home_score, existing.away_score = a_sets, b_sets
                existing.home_games, existing.away_games = a_games, b_games
            else:
                existing.home_score, existing.away_score = b_sets, a_sets
                existing.home_games, existing.away_games = b_games, a_games
            existing.status = "completed"
            counts["completed"] += 1
    session.flush()
    return counts


def sync(session: Session, days_ahead: int = 3) -> dict:
    """Pull the tournaments in progress now and the next few days, ATP and WTA."""
    rows: dict[str, dict] = {}
    today = datetime.now(UTC).date()
    errors = 0
    for tour_slug, tour in TOURS.items():
        days: list[str | None] = [None] + [
            (today + timedelta(days=d)).strftime("%Y%m%d") for d in range(1, days_ahead + 1)
        ]
        for day in days:
            try:
                payload = fetch_scoreboard(tour_slug, day)
            except Exception as exc:  # noqa: BLE001 - the source can change; never break the caller
                errors += 1
                logger.warning("tennis scoreboard %s %s failed: %s", tour_slug, day, exc)
                continue
            for row in parse_scoreboard(payload, tour):
                rows[row["external_id"]] = row
    if not rows:
        return {"matches": 0, "errors": errors}
    counts = upsert(session, list(rows.values()))
    session.commit()
    counts.update({"matches": len(rows), "errors": errors})
    return counts
