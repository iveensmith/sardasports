"""Ingest competitions from API-Football: lower divisions and domestic cups.

Football-Data.co.uk publishes none of these, so the registry in
`ml.api_competitions` is sourced here. One request returns a whole
competition-season (a 126-fixture Copa del Rey, a 308-fixture Segunda Liga),
which is why this is cheap once the plan allows it.

Usage:
    # What would it fetch, and how many requests would that cost?
    uv run python scripts/fetch_api_competitions.py --plan

    # Fetch (the daily request cap defaults to the free plan's 100)
    uv run python scripts/fetch_api_competitions.py --scope core --max-requests 2000

    # Pair existing clubs with API ids first — see "Club identity" below
    uv run python scripts/fetch_api_competitions.py --map-teams

    # Replay a saved response, writing nothing
    uv run python scripts/fetch_api_competitions.py --dry-run --competition-id 143 \
        --from-file fx.json --season 2024

Four things this gets right that a naive loader would not
---------------------------------------------------------
**The 90-minute score.** The engine predicts the 1X2 market on the 90-minute
result. The API's top-level `goals` includes extra time, so a match settled
after extra time would be recorded with a winner it did not have at 90 minutes
and its 1X2 label would be wrong. `score.fulltime` is the 90-minute score and
is the one used. About one single-leg cup tie in six is affected, and all 22 of
them in Copa del Rey 2024 were level at 90. In a two-legged tie extra time is
triggered by the *aggregate*, so a second leg's own 90-minute score need not be
level (a Champions League qualifier went to penalties after a 0-1 second leg) —
which is another reason to read the field and not assume.

**Neutral ground.** Matches in a registry competition's `neutral_rounds`
(every cup final; the FA Cup semi-finals) are flagged neutral, so Elo gives
neither side a home edge.

**Season labels.** The API names a season by the year it starts. Ours are
"2024-2025" for a split-year competition and "2025" for a calendar-year one.
Which a competition is, is recorded in the registry from the season start dates
the API publishes — not inferred from the matches in a batch, which would label
a partial refetch differently from the full season it belongs to.

**Club identity.** The two sources name clubs differently, and a mismatch gives
one club two short, meaningless rating histories. Clubs are resolved by API id
first, then exact and accent-folded name, and a club that matches neither is
*created* — never fuzzy-matched against the whole database, which paired
"Atletico Madrid" with a Brazilian club on real data. Existing clubs get their
ids from `--map-teams`, which pairs each league's API roster with ours
one-to-one (`app.services.team_identity`). Every created club is written to a
review file, because a new row is either a genuinely new club or a missed
alias, and only a person can tell which.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

from app.database.session import SessionLocal
from app.models.match import Match
from app.models.team import Team
from app.services.team_identity import TeamResolver, assign_clubs, similarity, tokens
from app.utils.config import get_settings
from app.utils.seasons import season_start_year
from ml.api_competitions import API_COMPETITIONS, BY_ID, ApiCompetition
from scripts.fetch_upcoming_fixtures import EXCLUDED_TEAM_PATTERN

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Statuses that mean the match was played to a result. Awarded and walkover
# results (AWD, WO) are excluded: nobody scored, so they say nothing about how
# the two teams play.
FINISHED = frozenset({"FT", "AET", "PEN"})

# The free plan allows 10 requests a minute; 6.5s keeps clear of it. A paid plan allows
# hundreds a minute, so `main` shortens this when the account is positively on one (a run
# of 600 requests is then minutes instead of over an hour).
REQUEST_SPACING_SECONDS = 6.5
PAID_REQUEST_SPACING_SECONDS = 0.3

REPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


# --- pure parsing ----------------------------------------------------------


def season_label(season_year: int, split_year: bool) -> str:
    """The season as we label it: "2024-2025" if split-year, "2025" if calendar-year.

    `split_year` is a fixed property of the competition (see
    `ml.api_competitions`), never inferred from the matches in hand: a partial
    refetch containing only April's cup final would otherwise be labelled
    "2024" and land beside, rather than inside, its own season.
    """
    return f"{season_year}-{season_year + 1}" if split_year else str(season_year)


def _parse_kickoff(raw: str) -> datetime:
    """An API ISO timestamp as a naive UTC datetime, as the database stores them."""
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def parse_fixture(item: dict, comp: ApiCompetition) -> dict | None:
    """One API fixture as a row, or None if it is not a finished result.

    The score is `score.fulltime`, the 90-minute result — see the module
    docstring for why `goals` is the wrong field.
    """
    fixture = item.get("fixture") or {}
    if (fixture.get("status") or {}).get("short") not in FINISHED:
        return None

    score = item.get("score") or {}
    full = score.get("fulltime") or {}
    if full.get("home") is None or full.get("away") is None:
        return None

    half = score.get("halftime") or {}
    teams = item.get("teams") or {}
    home, away = teams.get("home") or {}, teams.get("away") or {}
    if not home.get("name") or not away.get("name"):
        return None

    # Under-age and reserve sides: only for feeds that mix them in with senior
    # ones (Friendlies). A registered league's reserve sides are real members.
    if comp.exclude_youth and (
        EXCLUDED_TEAM_PATTERN.search(home["name"]) or EXCLUDED_TEAM_PATTERN.search(away["name"])
    ):
        return None

    round_name = (item.get("league") or {}).get("round")
    return {
        "external_id": f"apif-{fixture['id']}",
        "kickoff": _parse_kickoff(fixture["date"]),
        "competition": comp.name,
        "neutral_venue": comp.is_neutral(round_name),
        "round": round_name,
        "home_name": home["name"],
        "home_api_id": home.get("id"),
        "away_name": away["name"],
        "away_api_id": away.get("id"),
        "home_score": int(full["home"]),
        "away_score": int(full["away"]),
        "home_ht_goals": half.get("home"),
        "away_ht_goals": half.get("away"),
        # Kept for the log, not stored: whether the tie needed more than 90 minutes.
        "beyond_90": fixture["status"]["short"] in ("AET", "PEN"),
    }


# --- ingestion -------------------------------------------------------------


def ingest_competition_season(
    session, comp: ApiCompetition, season_year: int, items: list[dict], resolver: TeamResolver
) -> dict:
    """Insert one competition-season's finished matches; returns counts.

    A fixture already held — under this ingest's id, or under a CSV id from an
    earlier source — is not inserted again. If it went beyond 90 minutes and the
    stored score is not the 90-minute one, it is *corrected*: the first loader
    for national teams read the API's headline score, which includes extra time.
    """
    rows = [r for r in (parse_fixture(item, comp) for item in items) if r is not None]
    counts = {
        "fetched": len(items),
        "finished": len(rows),
        "inserted": 0,
        "existing": 0,
        "corrected": 0,
    }
    if not rows:
        return counts

    label = season_label(season_year, comp.split_year)
    existing_ids = {
        eid
        for (eid,) in session.query(Match.external_id).filter(Match.competition == comp.name)
        if eid
    }
    # Matched by teams and date, across every season of the competition: an older
    # loader may have filed the same fixture under a different season label.
    by_pair: dict[tuple[int, int], list[Match]] = defaultdict(list)
    for m in session.query(Match).filter(Match.competition == comp.name):
        by_pair[(m.home_team_id, m.away_team_id)].append(m)

    for row in rows:
        if row["external_id"] in existing_ids:
            counts["existing"] += 1
            continue
        home = resolver.resolve(row["home_name"], row["home_api_id"], comp.name)
        away = resolver.resolve(row["away_name"], row["away_api_id"], comp.name)
        held = next(
            (
                m
                for m in by_pair[(home.id, away.id)]
                if abs(m.match_date - row["kickoff"]) <= timedelta(days=1)
            ),
            None,
        )
        if held is not None:
            counts["existing"] += 1
            wrong = (held.home_score, held.away_score) != (row["home_score"], row["away_score"])
            if row["beyond_90"] and held.status == "completed" and wrong:
                held.home_score, held.away_score = row["home_score"], row["away_score"]
                counts["corrected"] += 1
            continue
        session.add(
            Match(
                external_id=row["external_id"],
                match_date=row["kickoff"],
                competition=comp.name,
                season=label,
                neutral_venue=row["neutral_venue"],
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=row["home_score"],
                away_score=row["away_score"],
                home_ht_goals=row["home_ht_goals"],
                away_ht_goals=row["away_ht_goals"],
                status="completed",
            )
        )
        existing_ids.add(row["external_id"])
        counts["inserted"] += 1
    session.flush()
    return counts


def apply_team_mapping(
    session, competition: str, season_label_: str, api_clubs: list[tuple[int, str]]
) -> dict:
    """Give existing clubs their API id, pairing a league's rosters one-to-one.

    Only confident pairs are written. The rest are returned for a person to
    read; nothing is guessed.
    """
    ours_ids = {
        tid
        for (h, a) in session.query(Match.home_team_id, Match.away_team_id).filter(
            Match.competition == competition, Match.season == season_label_
        )
        for tid in (h, a)
    }
    teams = {t.id: t for t in session.query(Team).filter(Team.id.in_(ours_ids))}
    names = [t.name for t in teams.values()]
    by_name = {t.name: t for t in teams.values()}

    written, review = 0, []
    for match in assign_clubs(api_clubs, names):
        if match.needs_review or match.our_name is None:
            review.append(match)
            continue
        team = by_name[match.our_name]
        if team.api_football_id is None:
            team.api_football_id = match.api_id
            written += 1
    session.flush()
    return {"written": written, "review": review, "api_clubs": len(api_clubs)}


# --- API access ------------------------------------------------------------


class Budget:
    """Counts requests so a run cannot spend more than it was given."""

    def __init__(self, limit: int) -> None:
        self.limit, self.used = limit, 0

    def spend(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


def api_get(path: str, params: dict, settings, timeout: int = 90) -> dict:
    response = requests.get(
        f"{settings.api_football_base_url}{path}",
        params=params,
        headers={"x-apisports-key": settings.api_football_key},
        timeout=timeout,
    )
    if response.status_code == 429:
        raise RuntimeError("rate limited (HTTP 429) — stopping so the rest can resume later")
    response.raise_for_status()
    return response.json()


def seasons_for(comp: ApiCompetition, wanted: tuple[int, int] | None) -> list[int]:
    lo, hi = comp.first_season, comp.last_season
    if wanted:
        lo, hi = max(lo, wanted[0]), min(hi, wanted[1])
    return list(range(lo, hi + 1))


def selected(scope: str, ids: set[int] | None) -> list[ApiCompetition]:
    out = []
    for comp in API_COMPETITIONS:
        if ids is not None:
            if comp.api_id in ids:
                out.append(comp)
        elif scope == "all" or comp.scope == scope:
            out.append(comp)
    return out


ALIAS_SUSPECT_AT = 0.8


def likely_aliases(
    session, created: list[tuple[str, int | None, str]]
) -> dict[str, tuple[str, float]]:
    """For each newly created club, the existing club it most resembles, if close.

    Informational, never acted on: a created row is either a genuinely new club
    or a missed alias, and only a person can tell which. Candidates are limited
    to clubs sharing at least one distinctive word, so this stays fast across
    thousands of clubs.
    """
    created_names = {name for name, _, _ in created}
    by_token: dict[str, list[str]] = defaultdict(list)
    for (name,) in session.query(Team.name).filter(Team.sport == "football"):
        if name in created_names:
            continue
        for token in set(tokens(name)):
            by_token[token].append(name)

    found: dict[str, tuple[str, float]] = {}
    for name, _, _ in created:
        candidates = {c for tok in set(tokens(name)) for c in by_token.get(tok, ())}
        scored = [(similarity(name, c), c) for c in candidates]
        if scored:
            best_score, best = max(scored)
            if best_score >= ALIAS_SUSPECT_AT:
                found[name] = (best, round(best_score, 2))
    return found


def write_new_teams_report(
    created: list[tuple[str, int | None, str]], suspects: dict[str, tuple[str, float]] | None = None
) -> Path | None:
    if not created:
        return None
    suspects = suspects or {}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "api_new_teams.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "api_id", "first_seen_in", "resembles_existing", "similarity"])
        for name, api_id, where in created:
            match, score = suspects.get(name, ("", ""))
            writer.writerow([name, api_id, where, match, score])
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ingest API-Football competitions")
    parser.add_argument("--scope", default="core", choices=["core", "extended", "all"])
    parser.add_argument(
        "--ids", default=None, help="Comma-separated API league ids (overrides scope)"
    )
    parser.add_argument("--seasons", default=None, help="Season years, e.g. 2022-2026")
    parser.add_argument("--max-requests", type=int, default=100, help="Request cap for this run")
    parser.add_argument(
        "--plan", action="store_true", help="Print what would be fetched; no requests"
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and count, but write nothing")
    parser.add_argument("--no-elo", action="store_true", help="Skip rebuilding Elo history")
    parser.add_argument("--refetch", action="store_true", help="Refetch seasons already ingested")
    parser.add_argument("--map-teams", action="store_true", help="Pair existing clubs with API ids")
    parser.add_argument("--from-file", default=None, help="Ingest a saved /fixtures response")
    parser.add_argument("--competition-id", type=int, default=None, help="With --from-file")
    parser.add_argument("--season", type=int, default=None, help="With --from-file")
    args = parser.parse_args(argv)

    if not args.plan and not args.from_file:
        from app.services.api_budget import is_paid_plan

        global REQUEST_SPACING_SECONDS
        if is_paid_plan(get_settings()):
            REQUEST_SPACING_SECONDS = PAID_REQUEST_SPACING_SECONDS
            logger.info("paid plan: %.1fs between requests", REQUEST_SPACING_SECONDS)

    wanted = None
    if args.seasons:
        lo, _, hi = args.seasons.partition("-")
        wanted = (int(lo), int(hi or lo))
    ids = {int(i) for i in args.ids.split(",")} if args.ids else None
    comps = selected(args.scope, ids)

    if args.plan:
        total = sum(len(seasons_for(c, wanted)) for c in comps)
        for comp in comps:
            seasons = seasons_for(comp, wanted)
            span = f"{seasons[0]}-{seasons[-1]}" if seasons else "none in range"
            logger.info("%-44s %2d season(s) %s", comp.name, len(seasons), span)
        logger.info("%d competitions, %d requests (one per competition-season)", len(comps), total)
        return

    session = SessionLocal()
    resolver = TeamResolver(session)
    try:
        if args.from_file:
            comp = BY_ID[args.competition_id]
            items = json.loads(Path(args.from_file).read_text(encoding="utf-8"))["response"]
            counts = ingest_competition_season(session, comp, args.season, items, resolver)
            logger.info("%s %s: %s", comp.name, args.season, counts)
            logger.info("new clubs created: %d", len(resolver.created))
        else:
            settings = get_settings()
            if not settings.api_football_key:
                raise SystemExit("API_FOOTBALL_KEY is not set.")
            budget = Budget(args.max_requests)
            if args.map_teams:
                _map_teams(session, settings, budget, wanted, ids)
            else:
                _fetch_all(
                    session,
                    comp_list=comps,
                    wanted=wanted,
                    settings=settings,
                    budget=budget,
                    resolver=resolver,
                    refetch=args.refetch,
                )
            logger.info("requests used: %d of %d", budget.used, budget.limit)

        if args.dry_run:
            session.rollback()
            logger.info("dry run: nothing written")
            return
        session.commit()
        suspects = likely_aliases(session, resolver.created)
        report = write_new_teams_report(resolver.created, suspects)
        if report:
            logger.info(
                "%d new clubs created, %d resemble an existing club — review %s",
                len(resolver.created),
                len(suspects),
                report,
            )
        if not args.no_elo and not args.map_teams:
            from scripts.load_to_db import rebuild_elo_history

            rebuild_elo_history(session, get_settings())
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _already_ingested(session, comp: ApiCompetition, season_year: int) -> bool:
    """A finished past season never changes; the current one always might.

    Decided by the season label the loaded matches carry, not by a date window: a window wide
    enough to hold a season also holds the start of the next one, and a final played in June
    (every Champions League and Conference League final, and some Europa League ones) made the
    following season look already loaded, so it was never fetched.
    """
    if season_year >= datetime.now(UTC).year:
        return False
    return (
        session.query(Match.id)
        .filter(
            Match.competition == comp.name,
            Match.external_id.like("apif-%"),
            Match.season == season_label(season_year, comp.split_year),
        )
        .first()
        is not None
    )


def _fetch_all(session, comp_list, wanted, settings, budget, resolver, refetch) -> None:
    for comp in comp_list:
        for year in seasons_for(comp, wanted):
            if not refetch and _already_ingested(session, comp, year):
                continue
            if not budget.spend():
                logger.warning("request cap reached — rerun to continue where this stopped")
                return
            try:
                body = api_get("/fixtures", {"league": comp.api_id, "season": year}, settings)
            except RuntimeError as exc:
                logger.warning("%s", exc)
                return
            if body.get("errors"):
                logger.warning("%s %s: skipped — %s", comp.name, year, body["errors"])
                time.sleep(REQUEST_SPACING_SECONDS)
                continue
            counts = ingest_competition_season(
                session, comp, year, body.get("response", []), resolver
            )
            session.commit()  # progress survives an interrupted run
            logger.info("%s %s: %s", comp.name, year, counts)
            time.sleep(REQUEST_SPACING_SECONDS)


def _stored_labels(session, competition: str, year: int) -> set[str]:
    """The season labels a competition holds that begin in `year`."""
    return {
        s
        for (s,) in session.query(Match.season).filter(Match.competition == competition).distinct()
        if season_start_year(s) == year
    }


def _map_teams(session, settings, budget, wanted, league_ids: set[int] | None = None) -> None:
    """Pair each existing league's API roster with ours, one league-season at a time.

    `league_ids` restricts it to those leagues. A season we hold no matches for is
    skipped *before* asking the API, so a request is never spent on a roster there
    is nothing to pair it with.
    """
    from scripts.fetch_upcoming_fixtures import LEAGUE_ID_TO_COMPETITION

    hi = datetime.now(UTC).year
    lo, hi = wanted if wanted else (hi - 2, hi - 1)
    report: list[tuple[str, str, str, float]] = []
    for league_id, competition in LEAGUE_ID_TO_COMPETITION.items():
        if league_ids is not None and league_id not in league_ids:
            continue
        for year in range(lo, hi + 1):
            labels = _stored_labels(session, competition, year)
            if not labels:
                continue
            if not budget.spend():
                logger.warning("request cap reached")
                return
            body = api_get("/teams", {"league": league_id, "season": year}, settings)
            if body.get("errors"):
                logger.warning("%s %s: skipped — %s", competition, year, body["errors"])
                time.sleep(REQUEST_SPACING_SECONDS)
                continue
            clubs = [(t["team"]["id"], t["team"]["name"]) for t in body.get("response", [])]
            for label in labels:
                result = apply_team_mapping(session, competition, label, clubs)
                logger.info(
                    "%s %s: wrote %d ids, %d to review",
                    competition,
                    label,
                    result["written"],
                    len(result["review"]),
                )
                report += [(competition, label, m.api_name, m.score) for m in result["review"]]
            session.commit()
            time.sleep(REQUEST_SPACING_SECONDS)
    if report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORT_DIR / "team_mapping_review.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["competition", "season", "api_name", "score"])
            writer.writerows(report)
        logger.info("wrote %s — read it before trusting those clubs", path)


if __name__ == "__main__":
    main()
