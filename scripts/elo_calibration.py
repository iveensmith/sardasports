"""Is the Elo estimator's confidence justified, in hindsight?

A prediction engine can be wrong in two different ways, and only one of them
is visible on a board. It can pick the wrong side — obvious, and the accuracy
metrics already cover it. Or it can pick the *right* side at the wrong price,
which no accuracy number catches: a model that says 55% about fixtures the
favourite wins 67% of the time is right about who wins and badly wrong about
how likely it was. That second failure is what makes a board look untrustworthy
to anyone who knows the sport, and it is what this script measures.

Method
------
Walk forward through every completed match in date order. For each one,
predict using only ratings built from strictly earlier matches, score the
prediction, and *then* apply the result. Nothing is ever scored against a
match it has already absorbed, so a scheme cannot be rewarded for fitting its
own training data. (Prequential evaluation: no held-out split is needed, and
every match gets used for both jobs in the right order.)

Then bucket by the favourite's predicted win probability and compare the
prediction with what actually happened. A well-calibrated estimator's buckets
sit on the diagonal: when it says 70%, the favourite wins about 70% of the
time. Pools are reported separately — club and international football have
very different amounts of data behind them, and averaging the two hides
exactly the problem this script exists to find.

Usage
-----
    uv run python scripts/elo_calibration.py
    uv run python scripts/elo_calibration.py --sweep      # compare K schemes
    uv run python scripts/elo_calibration.py --flat-k     # ignore weighting

Read the `gap` column. Anything beyond about 5 points in a bucket with a few
hundred matches in it is a real miscalibration worth chasing; a large gap in a
bucket of 30 is noise. `log loss` is the single-number summary and rewards
being both calibrated *and* decisive, so use it to choose between schemes and
the buckets to understand why one wins.
"""

from __future__ import annotations

import argparse
import math
import statistics
from collections import defaultdict

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.match import Match
from app.utils.config import get_settings
from ml.competitions import INTERNATIONAL_COMPETITIONS
from ml.elo.engine import EloEngine, MatchResult
from ml.elo.football import FOOTBALL_COMPETITION_K, INTERNATIONAL_ELO_K

BUCKET_MIN = 25  # below this a bucket's "actual" rate is noise, so don't print it


def pool_of(competition: str | None) -> str:
    return "international" if competition in INTERNATIONAL_COMPETITIONS else "club"


class Report:
    """Per-pool calibration counters."""

    def __init__(self) -> None:
        self.buckets: dict[tuple[str, int], dict] = defaultdict(
            lambda: {"n": 0, "pred_fav": 0.0, "act_fav": 0, "pred_draw": 0.0, "act_draw": 0}
        )
        self.log_loss: dict[str, list] = defaultdict(lambda: [0.0, 0])
        self.ratings: dict[str, dict[str, float]] = defaultdict(dict)

    def record(self, pool, probs, outcome, home_fav_prob, away_fav_prob):
        home_win, draw, away_win = probs
        self.log_loss[pool][0] += -math.log(
            max({"home": home_win, "draw": draw, "away": away_win}[outcome], 1e-12)
        )
        self.log_loss[pool][1] += 1

        home_is_favourite = home_fav_prob >= away_fav_prob
        predicted = home_fav_prob if home_is_favourite else away_fav_prob
        actual = outcome == ("home" if home_is_favourite else "away")

        bucket = self.buckets[(pool, min(int(predicted * 10), 9))]
        bucket["n"] += 1
        bucket["pred_fav"] += predicted
        bucket["act_fav"] += actual
        bucket["pred_draw"] += draw
        bucket["act_draw"] += outcome == "draw"

    def print(self, label: str) -> None:
        print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")
        for pool in ("international", "club"):
            total, summed = self.log_loss[pool][1], self.log_loss[pool][0]
            if not total:
                continue
            print(f"\n[{pool}]  log loss {summed / total:.4f}  over {total} matches")
            print(
                f"   {'predicted':>11} {'n':>7} {'pred':>6} {'actual':>7} {'gap':>7}"
                f"  | {'drawP':>6} {'drawA':>6} {'gap':>6}"
            )
            worst = 0.0
            for decile in range(10):
                bucket = self.buckets.get((pool, decile))
                if not bucket or bucket["n"] < BUCKET_MIN:
                    continue
                n = bucket["n"]
                pred = bucket["pred_fav"] / n * 100
                actual = bucket["act_fav"] / n * 100
                pred_draw = bucket["pred_draw"] / n * 100
                act_draw = bucket["act_draw"] / n * 100
                flag = "  <--" if abs(actual - pred) >= 5 else ""
                print(
                    f"   {decile * 10:>4}-{decile * 10 + 10:<6} {n:>7} {pred:>6.1f} "
                    f"{actual:>7.1f} {actual - pred:>+7.1f}  | {pred_draw:>6.1f} "
                    f"{act_draw:>6.1f} {act_draw - pred_draw:>+6.1f}{flag}"
                )
                worst = max(worst, abs(actual - pred))
            print(f"   worst favourite gap: {worst:.1f} points")

            ratings = sorted(self.ratings[pool].values())
            if len(ratings) >= 5:
                spread = ratings[-1] - ratings[0]
                print(
                    f"   rating spread: n={len(ratings)} "
                    f"sd={statistics.pstdev(ratings):.1f} min={ratings[0]:.0f} "
                    f"max={ratings[-1]:.0f} range={spread:.0f}"
                )


def walk_forward(matches, competition_k, settings) -> Report:
    """Score every match against ratings built only from earlier ones."""
    report = Report()
    # One engine per sport, for the same reason scripts/load_to_db.py uses
    # one: a shared engine keyed by team name would merge same-named
    # competitors from different sports into one rating history.
    engines: dict[str, EloEngine] = {}

    for match in matches:
        engine = engines.setdefault(
            match["sport"],
            EloEngine(
                k_factor=settings.elo_k_factor,
                home_advantage=settings.elo_home_advantage,
                initial_rating=settings.elo_initial_rating,
                competition_k=competition_k if match["sport"] == "football" else None,
            ),
        )
        if match["sport"] != "football":
            continue

        pool = pool_of(match["competition"])
        probs = engine.result_probabilities(
            match["home_team"], match["away_team"], neutral_venue=match["neutral_venue"]
        )
        home_score, away_score = match["home_score"], match["away_score"]
        outcome = (
            "home" if home_score > away_score else "away" if home_score < away_score else "draw"
        )
        report.record(pool, probs, outcome, probs[0], probs[2])

        engine.apply_result(
            MatchResult(
                home_team=match["home_team"],
                away_team=match["away_team"],
                home_score=home_score,
                away_score=away_score,
                match_date=match["match_date"],
                neutral_venue=match["neutral_venue"],
                competition=match["competition"],
            )
        )
        for team in (match["home_team"], match["away_team"]):
            report.ratings[pool][team] = engine.get_rating(team)

    return report


def load_matches(session) -> list[dict]:
    """Completed football matches, oldest first, as plain dicts."""
    from app.models.team import Team

    home, away = Team.__table__.alias("home"), Team.__table__.alias("away")
    rows = session.execute(
        select(
            Match.sport,
            Match.competition,
            Match.match_date,
            Match.neutral_venue,
            Match.home_score,
            Match.away_score,
            home.c.name.label("home_team"),
            away.c.name.label("away_team"),
        )
        .join(home, home.c.id == Match.home_team_id)
        .join(away, away.c.id == Match.away_team_id)
        .where(
            Match.status == "completed",
            Match.home_score.is_not(None),
            Match.away_score.is_not(None),
        )
        .order_by(Match.match_date.asc(), Match.id.asc())
    ).all()
    return [
        {
            "sport": r.sport,
            "competition": r.competition,
            "match_date": r.match_date,
            "neutral_venue": bool(r.neutral_venue),
            "home_score": r.home_score,
            "away_score": r.away_score,
            "home_team": r.home_team,
            "away_team": r.away_team,
        }
        for r in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--flat-k",
        action="store_true",
        help="Score with a flat K, ignoring competition weighting (the pre-fix behaviour).",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Compare several K schemes on the same matches.",
    )
    args = parser.parse_args()

    settings = get_settings()
    session = SessionLocal()
    try:
        matches = load_matches(session)
    finally:
        session.close()
    print(f"{len(matches)} completed matches loaded")

    if args.sweep:
        schemes = {
            "flat K=20 (pre-fix)": None,
            "competition-weighted (current)": FOOTBALL_COMPETITION_K,
            "flat international K=45": dict.fromkeys(INTERNATIONAL_ELO_K, 45.0),
            "flat international K=70": dict.fromkeys(INTERNATIONAL_ELO_K, 70.0),
        }
        for label, scheme in schemes.items():
            walk_forward(matches, scheme, settings).print(label)
        return

    scheme = None if args.flat_k else FOOTBALL_COMPETITION_K
    label = "flat K=20" if args.flat_k else "competition-weighted K"
    walk_forward(matches, scheme, settings).print(label)


if __name__ == "__main__":
    main()
