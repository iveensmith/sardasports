"""One competition, as a reader landing on its page wants to see it.

Everything here is counted from matches we hold, or is the engine's own
settled record for the competition. Nothing is a claim about the competition
that the data does not carry: the rates are rates over completed matches on
record, the table is the table of those results, and "hot" and "cold" are a
stated rule over the last five results — not a rating.

Two things are deliberately absent for international competitions. A league
table of friendlies, or of qualifiers played in three groups over two years,
is not a table of anything; and "form over the last five" mixes opponents
from different continents. A competition with `is_international` therefore
gets the rates, the record and the fixtures, and no table or form.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.team import Team
from app.services.base_rates import market_base_rates
from app.services.board_service import build_row, slugify
from app.services.progress_service import competition_record
from app.services.standings_service import compute_standings
from app.services.stored_predictions import predict_with_stored_fallback
from ml.competition_catalogue import BY_COMPETITION, CompetitionMeta
from ml.competitions import INTERNATIONAL_COMPETITIONS

# How many fixtures and results the page lists. A page, not an archive: the
# full board for any day is one link away.
FIXTURE_LIMIT = 10
RESULT_LIMIT = 10

# A team needs this many matches in the season before its form is a verdict.
FORM_WINDOW = 5

# "Hot" and "cold" describe now. If a competition's newest result is older
# than this, the last five matches are last season's, and naming a hot team
# from them would present history as current form.
FORM_MAX_AGE_DAYS = 45


def slug_for(competition: str) -> str:
    return slugify(competition)


def competition_for_slug(slug: str) -> CompetitionMeta | None:
    """Resolve a URL slug to a catalogued competition, or None."""
    for meta in BY_COMPETITION.values():
        if slug_for(meta.competition) == slug:
            return meta
    return None


def season_label(season: str | None) -> str | None:
    """A season code as a reader would write it.

    Calendar-year leagues are stored under codes that were built for split
    seasons: Argentina's 2025 is "2525" (the halves "25" and "25" read as a
    pair) and MLS's is "2025-2025". Neither says what it means, so a season
    whose two halves are the same year is shown as that one year. The stored
    value is left alone — it is a key, and changing it rewrites history.
    """
    if season is None:
        return None
    if len(season) == 4 and season.isdigit() and season[:2] == season[2:]:
        return f"20{season[:2]}"
    if len(season) == 9 and season[:4] == season[5:]:
        return season[:4]
    return season


def _pct(part: int, whole: int) -> float | None:
    """A rate to one decimal, or None where there is nothing to divide."""
    return round(100 * part / whole, 1) if whole else None


def _outcome_rates(rows) -> dict:
    """Result split and goals rates over a set of (home_score, away_score)."""
    total = len(rows)
    home = sum(1 for h, a in rows if h > a)
    draw = sum(1 for h, a in rows if h == a)
    away = total - home - draw
    return {
        "matches": total,
        "home_win": _pct(home, total),
        "draw": _pct(draw, total),
        "away_win": _pct(away, total),
        "over_1_5": _pct(sum(1 for h, a in rows if h + a > 1), total),
        "over_2_5": _pct(sum(1 for h, a in rows if h + a > 2), total),
        "over_3_5": _pct(sum(1 for h, a in rows if h + a > 3), total),
        "btts": _pct(sum(1 for h, a in rows if h > 0 and a > 0), total),
    }


def _recent_form(season_matches, names: dict[int, str]) -> list[dict]:
    """Each team's last five results this season, as points and a W/D/L string.

    Teams with fewer than five matches are left out rather than judged on a
    shorter run: "hot" over two games is a coincidence with a label on it.
    """
    per_team: dict[int, list[tuple[datetime, int, int, int]]] = defaultdict(list)
    for match in season_matches:
        per_team[match.home_team_id].append(
            (match.match_date, match.home_score, match.away_score, match.id)
        )
        per_team[match.away_team_id].append(
            (match.match_date, match.away_score, match.home_score, match.id)
        )

    form = []
    for team_id, played in per_team.items():
        played.sort()
        last = played[-FORM_WINDOW:]
        if len(last) < FORM_WINDOW:
            continue
        points = sum(3 if f > a else 1 if f == a else 0 for _, f, a, _ in last)
        goal_difference = sum(f - a for _, f, a, _ in last)
        form.append(
            {
                "team": names[team_id],
                "points": points,
                "goal_difference": goal_difference,
                "results": "".join("W" if f > a else "D" if f == a else "L" for _, f, a, _ in last),
            }
        )
    return form


def _hot_and_cold(form: list[dict]) -> tuple[dict | None, dict | None]:
    """The best and worst of the last five, goal difference breaking a tie."""
    if len(form) < 2:
        return None, None
    ordered = sorted(form, key=lambda f: (f["points"], f["goal_difference"], f["team"]))
    return ordered[-1], ordered[0]


def _fixtures(db: Session, competition: str) -> list[dict]:
    """The next fixtures, priced the way the board prices them."""
    now = datetime.now(UTC).replace(tzinfo=None)
    matches = (
        db.query(Match)
        .filter(
            Match.competition == competition,
            Match.status == "scheduled",
            Match.match_date >= now,
        )
        .order_by(Match.match_date.asc(), Match.id.asc())
        .limit(FIXTURE_LIMIT)
        .all()
    )
    if not matches:
        return []
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    names = {t.id: t.name for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
    base_rates = market_base_rates(db, "football")
    predictions = predict_with_stored_fallback(db, matches)
    return [
        build_row(
            match,
            prediction,
            base_rates,
            names.get(match.home_team_id, ""),
            names.get(match.away_team_id, ""),
        )
        for match, prediction in zip(matches, predictions, strict=True)
    ]


def _latest_results(db: Session, competition: str) -> list[dict]:
    """The last results on record, plain: no pick, because none is claimed."""
    matches = (
        db.query(Match)
        .filter(
            Match.competition == competition,
            Match.status == "completed",
            Match.home_score.is_not(None),
        )
        .order_by(Match.match_date.desc(), Match.id.desc())
        .limit(RESULT_LIMIT)
        .all()
    )
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    names = {t.id: t.name for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
    return [
        {
            "match_id": m.id,
            "match_date": m.match_date.isoformat(),
            "home_team": names.get(m.home_team_id, ""),
            "away_team": names.get(m.away_team_id, ""),
            "home_score": m.home_score,
            "away_score": m.away_score,
        }
        for m in matches
    ]


def build_league(db: Session, meta: CompetitionMeta) -> dict:
    competition = meta.competition

    completed = (
        db.query(Match)
        .filter(
            Match.competition == competition,
            Match.status == "completed",
            Match.home_score.is_not(None),
            Match.away_score.is_not(None),
        )
        .order_by(Match.match_date.asc())
        .all()
    )
    rates = _outcome_rates([(m.home_score, m.away_score) for m in completed])
    history = {
        **rates,
        "first": completed[0].match_date.date().isoformat() if completed else None,
        "last": completed[-1].match_date.date().isoformat() if completed else None,
    }

    season = None
    table: list[dict] = []
    teams = None
    hot = cold = None
    age_days = (
        (datetime.now(UTC).replace(tzinfo=None) - completed[-1].match_date).days
        if completed
        else None
    )
    if not meta.is_international and completed:
        season, standings = compute_standings(db, competition)
        table = [vars(row) for row in standings]
        teams = len(table)
        season_matches = [m for m in completed if m.season == season]
        names = {
            t.id: t.name
            for t in db.query(Team)
            .filter(
                Team.id.in_(
                    {m.home_team_id for m in season_matches}
                    | {m.away_team_id for m in season_matches}
                )
            )
            .all()
        }
        if age_days is not None and age_days <= FORM_MAX_AGE_DAYS:
            hot, cold = _hot_and_cold(_recent_form(season_matches, names))

    return {
        "competition": competition,
        "slug": slug_for(competition),
        "short_name": meta.short_name,
        "country": meta.country,
        "country_code": meta.country_code,
        "tier": meta.tier,
        "is_international": meta.is_international,
        # Not the same thing: the Champions League sits under "Europe" like the
        # Euros do, but is made of clubs, not national teams.
        "national_teams": competition in INTERNATIONAL_COMPETITIONS,
        "history": history,
        # Days since the newest result on record, so the page can say how
        # current the table and rates are rather than imply they are live.
        "last_match_age_days": age_days,
        "season": season_label(season),
        "teams": teams,
        "standings": table,
        # The stated rule behind "hot" and "cold", so the page can print it.
        "form_window": FORM_WINDOW,
        "hot_team": hot,
        "cold_team": cold,
        "record": competition_record(db, competition),
        "fixtures": _fixtures(db, competition),
        "results": _latest_results(db, competition),
    }
