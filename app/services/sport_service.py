"""What the site shows for each sport: how fresh the data is, who is rated highest,
what the engine would have said about the latest results, and how well each of its
models measures against the thing it has to beat.

Football has a live, stored-before-kick-off record and its own pages. Basketball and
tennis are served here, and they differ in one way that the site has to be honest
about: there is no live feed of fixtures for either. Tennis results come from
tennis-data.co.uk (results only, no schedule) and basketball from API-Basketball on a
plan that serves past seasons. So every figure below says what date the data runs to,
and "upcoming" is whatever is actually in the database, which may be nothing.

Nothing here is invented to fill a page. The "recent" rows are predictions the engine
makes *now* for matches that already finished, using only the results before each
match (the leakage rule in `prediction_service`), and they are labelled as
reconstructed, never as picks that were published in advance.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from time import monotonic

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import EloHistory, ModelVersion, SportPrediction
from app.models.match import Match
from app.models.team import Team
from app.services.prediction_service import predict_for_matches

logger = logging.getLogger(__name__)

# What each sport is called, who plays, and which models cover it. The model names are
# the ones the trainers register (see ml/training), in the order the page shows them.
SPORTS: dict[str, dict] = {
    "football": {
        "label": "Football",
        "competitor": "team",
        "models": [],
    },
    "basketball": {
        "label": "Basketball",
        "competitor": "team",
        "models": [
            ("lightgbm_basketball_winner", "Game winner, all leagues"),
            ("lightgbm_basketball_total_215_5", "NBA total points, over 215.5"),
            ("lightgbm_basketball_total_225_5", "NBA total points, over 225.5"),
            ("lightgbm_basketball_total_235_5", "NBA total points, over 235.5"),
            ("statistical_basketball_totals", "Total points outside the NBA (statistical)"),
        ],
    },
    "tennis": {
        "label": "Tennis",
        "competitor": "player",
        "models": [
            ("lightgbm_tennis_winner", "Match winner"),
            ("lightgbm_tennis_total_games_19_5", "Total games, over 19.5"),
            ("lightgbm_tennis_total_games_21_5", "Total games, over 21.5"),
            ("lightgbm_tennis_total_games_23_5", "Total games, over 23.5"),
        ],
    },
}

# A baseline is the simple rule a model has to beat to have shown any skill. The
# trainers each record the one that fits their market; a model with none is reported
# without a comparison rather than being flattered by an assumed 50%.
BASELINE_KEYS = [
    ("elo_baseline_accuracy", "Always pick the higher-rated side"),
    ("home_win_base_rate", "Always pick the home side"),
    ("majority_class_base_rate", "Always pick the more common result"),
]

TOP_RATED_LIMIT = 10
# A player or team counts as active if it played in the year before the data ends.
ACTIVE_WINDOW_DAYS = 365
RECENT_LIMIT = 8
# Fewer than this from one day and the page reaches back a day for more.
MIN_RECENT = 4
MAX_RECENT_DAYS = 4
UPCOMING_LIMIT = 12
UPCOMING_WINDOW_DAYS = 14

CACHE_TTL_SECONDS = 3600
# The home page and the sport tabs read this on every render, so it is kept briefly.
SUMMARY_TTL_SECONDS = 600
_SUMMARY_KEY = "__summary__"
_cache: dict[str, tuple[float, dict]] = {}


def clear_cache() -> None:
    """For tests, and after anything that changes what these pages should show."""
    _cache.clear()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def sports_summary(db: Session, *, max_age: float | None = None) -> dict:
    """One row per sport: how much is on record and how recent it is. Cached.

    `max_age` lets the warm-up job rebuild an answer before it lapses (see `sports_warm_job`),
    so a visitor is not the one who finds it expired.
    """
    cached = _cache.get(_SUMMARY_KEY)
    limit = SUMMARY_TTL_SECONDS if max_age is None else min(SUMMARY_TTL_SECONDS, max_age)
    if cached is not None and monotonic() - cached[0] < limit:
        return cached[1]
    try:
        result = _summary(db)
    except Exception:
        logger.exception("sports summary failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        if cached is not None:
            return {**cached[1], "stale": True}
        raise
    _cache[_SUMMARY_KEY] = (monotonic(), result)
    return result


def _summary(db: Session) -> dict:
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = (
        db.query(
            Match.sport,
            func.count(Match.id),
            func.max(Match.match_date),
        )
        .filter(Match.status == "completed")
        .group_by(Match.sport)
        .all()
    )
    completed = {sport: (count, last) for sport, count, last in rows}

    # For basketball and tennis only fixtures that carry a stored prediction count: a
    # match the engine could not price (a side with too little history) is not listed
    # anywhere on the site. Football has its own board and keeps every fixture.
    upcoming_rows = (
        db.query(Match.sport, func.count(Match.id), func.min(Match.match_date))
        .outerjoin(SportPrediction, SportPrediction.match_id == Match.id)
        .filter(
            Match.status == "scheduled",
            Match.match_date >= now,
            (Match.sport == "football") | SportPrediction.match_id.is_not(None),
        )
        .group_by(Match.sport)
        .all()
    )
    upcoming = {sport: (count, first) for sport, count, first in upcoming_rows}

    sports = []
    for key, spec in SPORTS.items():
        count, last = completed.get(key, (0, None))
        up_count, up_first = upcoming.get(key, (0, None))
        sports.append(
            {
                "sport": key,
                "label": spec["label"],
                "matches_on_record": count,
                "last_result_date": _iso(last),
                "upcoming_fixtures": up_count,
                "next_fixture_date": _iso(up_first),
            }
        )
    return {"sports": sports}


def _model_rows(db: Session, sport: str) -> list[dict]:
    rows = []
    for name, label in SPORTS[sport]["models"]:
        version = (
            db.query(ModelVersion)
            .filter(ModelVersion.model_name == name, ModelVersion.is_active.is_(True))
            .order_by(ModelVersion.trained_at.desc())
            .first()
        )
        metrics = (version.metrics or {}) if version else {}
        accuracy = metrics.get("accuracy")
        if not isinstance(accuracy, int | float):
            continue
        baseline = baseline_kind = None
        for key, kind in BASELINE_KEYS:
            value = metrics.get(key)
            if isinstance(value, int | float):
                baseline, baseline_kind = round(value * 100, 1), kind
                break
        # A model trained across several competitions also records how it did on each
        # group, against that group's own baseline; those become their own rows.
        for key, group_label in (
            ("nba", "Game winner, NBA only"),
            ("other_leagues", "Game winner, every other league"),
        ):
            group = (metrics.get("by_group") or {}).get(key)
            if group and isinstance(group.get("accuracy"), int | float):
                base = group.get("home_win_base_rate")
                rows.append(
                    {
                        "model": f"{name}#{key}",
                        "label": group_label,
                        "accuracy": round(group["accuracy"] * 100, 1),
                        "baseline": None if base is None else round(base * 100, 1),
                        "baseline_kind": "Always pick the home side",
                        "edge": (
                            None if base is None else round((group["accuracy"] - base) * 100, 1)
                        ),
                        "test_matches": group.get("num_test_samples"),
                        "trained_at": _iso(version.trained_at),
                    }
                )
        rows.append(
            {
                "model": name,
                "label": label,
                "accuracy": round(accuracy * 100, 1),
                "baseline": baseline,
                "baseline_kind": baseline_kind,
                "edge": None if baseline is None else round(accuracy * 100 - baseline, 1),
                "test_matches": metrics.get("num_test_samples"),
                "trained_at": _iso(version.trained_at),
            }
        )
    return rows


def _competitions(db: Session, sport: str) -> list[dict]:
    rows = (
        db.query(
            Match.competition,
            func.count(Match.id),
            func.min(Match.match_date),
            func.max(Match.match_date),
        )
        .filter(Match.sport == sport, Match.status == "completed")
        .group_by(Match.competition)
        .order_by(func.count(Match.id).desc())
        .all()
    )
    return [
        {"name": name, "matches": count, "first_date": _iso(first), "last_date": _iso(last)}
        for name, count, first, last in rows
    ]


def _top_rated(db: Session, sport: str, last_date: datetime | None) -> list[dict]:
    """The highest-rated competitors, grouped by the competition they last played in.

    Ratings are only comparable between competitors who play each other, so one list
    across everything would mislead: the ATP and the WTA never meet, and an NBA rating
    and a Greek league rating come from different pools. Each group is ranked alone.
    A competitor counts if it played in the last year of data, under the competition
    of its latest match.
    """
    if last_date is None:
        return []
    since = last_date - timedelta(days=ACTIVE_WINDOW_DAYS)
    latest_competition: dict[int, tuple[datetime, str]] = {}
    for column in (Match.home_team_id, Match.away_team_id):
        rows = (
            db.query(column, Match.match_date, Match.competition)
            .filter(Match.sport == sport, Match.status == "completed", Match.match_date >= since)
            .all()
        )
        for team_id, when, competition in rows:
            if team_id not in latest_competition or when > latest_competition[team_id][0]:
                latest_competition[team_id] = (when, competition)
    if not latest_competition:
        return []

    # The current rating is the last update in the Elo history. `teams.elo_rating`
    # is the column's default for most competitors and is not kept in step, so it is
    # not used here.
    latest = (
        db.query(func.max(EloHistory.id))
        .filter(EloHistory.team_id.in_(latest_competition))
        .group_by(EloHistory.team_id)
        .subquery()
    )
    rated = (
        db.query(EloHistory.team_id, EloHistory.rating_after)
        .filter(EloHistory.id.in_(db.query(latest)))
        .all()
    )
    names = {
        t.id: t.name
        for t in db.query(Team).filter(Team.id.in_([team_id for team_id, _ in rated])).all()
    }
    groups: dict[str, list[dict]] = {}
    for team_id, rating in rated:
        if team_id not in names:
            continue
        competition = latest_competition[team_id][1]
        groups.setdefault(competition, []).append(
            {"team_id": team_id, "name": names[team_id], "rating": round(rating)}
        )

    per_group, max_groups, min_size = (10, 2, 1) if sport == "tennis" else (5, 8, 8)
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    out = []
    for competition, teams in ordered:
        if len(teams) < min_size:
            continue
        teams.sort(key=lambda t: -t["rating"])
        out.append({"competition": competition, "teams": teams[:per_group]})
        if len(out) >= max_groups:
            break
    return out


def _winner_pick(payload: dict | None, home: str, away: str) -> dict | None:
    """Who the engine backs, from a two-way prediction (neither sport has a draw)."""
    if not payload:
        return None
    home_win, away_win = payload.get("home_win"), payload.get("away_win")
    if home_win is None or away_win is None:
        return None
    if home_win >= away_win:
        return {"name": home, "side": "home", "probability": round(home_win, 1)}
    return {"name": away, "side": "away", "probability": round(away_win, 1)}


def _match_row(match: Match, names: dict[int, str], payload: dict | None) -> dict:
    home, away = names.get(match.home_team_id, ""), names.get(match.away_team_id, "")
    row = {
        "match_id": match.id,
        "match_date": _iso(match.match_date),
        "competition": match.competition,
        "surface": match.surface,
        "home": home,
        "away": away,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "home_win": None if not payload else payload.get("home_win"),
        "away_win": None if not payload else payload.get("away_win"),
        "pick": _winner_pick(payload, home, away),
    }
    if match.home_score is not None and match.away_score is not None and row["pick"]:
        winner = "home" if match.home_score > match.away_score else "away"
        row["pick_correct"] = row["pick"]["side"] == winner
    else:
        row["pick_correct"] = None
    return row


def _names(db: Session, matches: list[Match]) -> dict[int, str]:
    ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    if not ids:
        return {}
    return {t.id: t.name for t in db.query(Team).filter(Team.id.in_(ids)).all()}


def _predict(db: Session, matches: list[Match]) -> list[dict | None]:
    """The engine's payload per match, or None where it has no basis for one.

    A side with too little history comes back from the engine with a near coin-flip
    number; that is not a prediction, so it is dropped here and the match is not listed.
    """
    if not matches:
        return []
    try:
        payloads = predict_for_matches(db, matches)
        return [
            None if p is None or p.get("thin_history") or p.get("home_win") is None else p
            for p in payloads
        ]
    except Exception:  # noqa: BLE001
        logger.exception("sport page predictions failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return [None] * len(matches)


def _recent(db: Session, sport: str) -> list[dict]:
    """The latest finished matches, with what the engine says about each now.

    Taken from the most recent day (and the day before only if that is too few to
    be worth showing): predictions load the sport's whole history once per day, and
    for tennis that is the slow part.
    """
    finished = (
        db.query(Match)
        .filter(Match.sport == sport, Match.status == "completed", Match.home_score.is_not(None))
        .order_by(Match.match_date.desc(), Match.id.desc())
        .limit(RECENT_LIMIT * 3)
        .all()
    )
    days: list = []
    for m in finished:
        if m.match_date.date() not in days:
            days.append(m.match_date.date())
    chosen: list[Match] = []
    for day in days[:MAX_RECENT_DAYS]:
        if len(chosen) >= MIN_RECENT:
            break
        chosen += [m for m in finished if m.match_date.date() == day]
    names = _names(db, chosen)
    payloads = _predict(db, chosen)
    # Matches the engine could not price are left out, and the list is filled from the
    # next ones, so a thin match never takes a place or shows without a prediction.
    rows = [_match_row(m, names, p) for m, p in zip(chosen, payloads, strict=True) if p is not None]
    return rows[:RECENT_LIMIT]


def _upcoming(db: Session, sport: str) -> list[dict]:
    now = datetime.now(UTC).replace(tzinfo=None)
    fixtures = (
        db.query(Match)
        .filter(
            Match.sport == sport,
            Match.status == "scheduled",
            Match.match_date >= now,
            Match.match_date < now + timedelta(days=UPCOMING_WINDOW_DAYS),
        )
        .order_by(Match.match_date.asc())
        .limit(UPCOMING_LIMIT * 3)
        .all()
    )
    names = _names(db, fixtures)
    payloads = _predict(db, fixtures)
    rows = [
        _match_row(m, names, p) for m, p in zip(fixtures, payloads, strict=True) if p is not None
    ]
    return rows[:UPCOMING_LIMIT]


def _compute(db: Session, sport: str) -> dict:
    spec = SPORTS[sport]
    last = (
        db.query(func.max(Match.match_date))
        .filter(Match.sport == sport, Match.status == "completed")
        .scalar()
    )
    total = (
        db.query(func.count(Match.id))
        .filter(Match.sport == sport, Match.status == "completed")
        .scalar()
    )
    first = (
        db.query(func.min(Match.match_date))
        .filter(Match.sport == sport, Match.status == "completed")
        .scalar()
    )
    competitors = (
        db.query(func.count(Team.id))
        .filter(
            Team.sport == sport,
            Team.id.in_(
                db.query(Match.home_team_id).filter(
                    Match.sport == sport, Match.status == "completed"
                )
            )
            | Team.id.in_(
                db.query(Match.away_team_id).filter(
                    Match.sport == sport, Match.status == "completed"
                )
            ),
        )
        .scalar()
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    return {
        "sport": sport,
        "label": spec["label"],
        "competitor": spec["competitor"],
        "matches_on_record": total,
        "competitors_on_record": competitors,
        "first_result_date": _iso(first),
        "last_result_date": _iso(last),
        "days_since_last_result": None if last is None else max(0, (now - last).days),
        "competitions": _competitions(db, sport),
        "top_rated": _top_rated(db, sport, last),
        "upcoming": _upcoming(db, sport),
        "recent": _recent(db, sport),
        "models": _model_rows(db, sport),
    }


def sport_overview(db: Session, sport: str, *, max_age: float | None = None) -> dict:
    """The full page payload for one sport. Cached; the last good answer survives a failure.

    `max_age` lets the warm-up job rebuild an answer before it lapses: pricing tennis loads the
    sport's whole history (several seconds), which should happen in that job, not in a request.
    """
    if sport not in SPORTS or not SPORTS[sport]["models"]:
        raise KeyError(sport)
    cached = _cache.get(sport)
    limit = CACHE_TTL_SECONDS if max_age is None else min(CACHE_TTL_SECONDS, max_age)
    if cached is not None and monotonic() - cached[0] < limit:
        return cached[1]
    try:
        result = _compute(db, sport)
    except Exception:
        logger.exception("sport overview failed for %s", sport)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        if cached is not None:
            return {**cached[1], "stale": True}
        raise
    _cache[sport] = (monotonic(), result)
    return result


__all__ = ["SPORTS", "clear_cache", "sport_overview", "sports_summary"]
