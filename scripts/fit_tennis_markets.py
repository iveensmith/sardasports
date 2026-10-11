"""Fit the tennis markets that sit behind "who wins", and report how well they price matches
they never saw.

Every market here is derived from one number the engine already has, the probability that a
player wins the match, plus the match's format (best of 3 or 5), surface and tour. What is
fitted is *how matches decay into sets and games around that number*, from 80,000 real
set-by-set results (`matches.period_scores`):

* set betting: given the favourite wins, how often in straight sets; given the underdog wins,
  likewise (best of 5 gets the full 3-0 / 3-1 / 3-2 split);
* the first set winner;
* the margin in games (its centre and its spread);
* whether there is a tiebreak, and how long the first set runs.

The match probability used for fitting is the walk-forward surface Elo (no match is rated by
anything that came after it). The live engine blends Elo with a trained model, which is a
little sharper, so these calibrations are, if anything, slightly conservative.

    python -m scripts.fit_tennis_markets            # evaluate, then write
    python -m scripts.fit_tennis_markets --no-write
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402

from app.database.session import SessionLocal  # noqa: E402
from app.models.match import Match  # noqa: E402
from app.models.team import Team  # noqa: E402
from ml.feature_engineering.tennis import SurfaceElo  # noqa: E402

PARAMS_PATH = ROOT / "ml" / "tennis_market_params.json"
CUT = datetime(2024, 1, 1)
MIN_PRIOR = 5
SURFACES = ("Hard", "Clay", "Grass")


def logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def load_frame() -> pd.DataFrame:
    session = SessionLocal()
    try:
        names = {t.id: t.name for t in session.query(Team).filter(Team.sport == "tennis")}
        rows = []
        for m in (
            session.query(Match)
            .filter(Match.sport == "tennis", Match.status == "completed")
            .order_by(Match.match_date.asc(), Match.id.asc())
        ):
            periods = m.period_scores
            if isinstance(periods, str):
                periods = json.loads(periods)
            rows.append(
                {
                    "date": m.match_date,
                    "home": names.get(m.home_team_id, ""),
                    "away": names.get(m.away_team_id, ""),
                    "tour": m.competition,
                    "surface": m.surface,
                    "best_of": m.best_of,
                    "home_sets": m.home_score,
                    "away_sets": m.away_score,
                    "sets": (periods or {}).get("sets"),
                }
            )
        return pd.DataFrame(rows)
    finally:
        session.close()


def with_probabilities(df: pd.DataFrame) -> pd.DataFrame:
    """Adds the walk-forward win probability for the home slot and prior-match counts."""
    elo = SurfaceElo()
    played: dict[str, int] = defaultdict(int)
    p_home, prior_h, prior_a = [], [], []
    for r in df.itertuples():
        surface = r.surface if r.surface in SURFACES else None
        a = elo.get(r.home, surface)
        b = elo.get(r.away, surface)
        p_home.append(SurfaceElo.expected(a, b))
        prior_h.append(played[r.home])
        prior_a.append(played[r.away])
        if r.home_sets > r.away_sets:
            elo.apply(r.home, r.away, surface)
        else:
            elo.apply(r.away, r.home, surface)
        played[r.home] += 1
        played[r.away] += 1
    out = df.copy()
    out["p_home"] = p_home
    out["prior_home"] = prior_h
    out["prior_away"] = prior_a
    return out


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["sets"].notna() & df["best_of"].isin([3, 5])].copy()
    d = d[(d["prior_home"] >= MIN_PRIOR) & (d["prior_away"] >= MIN_PRIOR)]
    d["fav_is_home"] = d["p_home"] >= 0.5
    d["p_fav"] = np.where(d["fav_is_home"], d["p_home"], 1 - d["p_home"])
    d["z"] = d["p_fav"].map(logit)
    d["fav_sets"] = np.where(d["fav_is_home"], d["home_sets"], d["away_sets"])
    d["dog_sets"] = np.where(d["fav_is_home"], d["away_sets"], d["home_sets"])
    d["fav_won"] = d["fav_sets"] > d["dog_sets"]
    d["home_games"] = d["sets"].map(lambda s: sum(x[0] for x in s))
    d["away_games"] = d["sets"].map(lambda s: sum(x[1] for x in s))
    d["margin"] = d["home_games"] - d["away_games"]
    d["set1_home"] = d["sets"].map(lambda s: 1 if s[0][0] > s[0][1] else 0)
    d["set1_games"] = d["sets"].map(lambda s: s[0][0] + s[0][1])
    d["tiebreak"] = d["sets"].map(lambda s: 1 if any(set(x) == {6, 7} for x in s) else 0)
    d["signed_logit"] = d["p_home"].map(logit)
    return d


# ---------------------------------------------------------------- fitting


def _logistic(x: np.ndarray, y: np.ndarray) -> dict:
    model = LogisticRegression(C=100.0, max_iter=500)
    model.fit(x, y)
    return {"intercept": float(model.intercept_[0]), "coef": [float(c) for c in model.coef_[0]]}


def _feature_row(z: float, surface: str | None, tour: str | None, best_of: int) -> list[float]:
    return [
        z,
        1.0 if surface == "Hard" else 0.0,
        1.0 if surface == "Clay" else 0.0,
        1.0 if surface == "Grass" else 0.0,
        1.0 if tour == "ATP" else 0.0,
        1.0 if best_of == 5 else 0.0,
    ]


def _matrix(d: pd.DataFrame) -> np.ndarray:
    return np.array(
        [
            _feature_row(z, s, t, b)
            for z, s, t, b in zip(d["z"], d["surface"], d["tour"], d["best_of"], strict=True)
        ]
    )


def fit(d: pd.DataFrame) -> dict:
    params: dict = {}
    # --- set betting, best of 3: P(straight sets | favourite wins) and | underdog wins
    for fmt in (3, 5):
        g = d[d["best_of"] == fmt]
        for who in ("fav", "dog"):
            winner = g[g["fav_won"]] if who == "fav" else g[~g["fav_won"]]
            loser_sets = np.where(who == "fav", winner["dog_sets"], winner["fav_sets"])
            x = winner[["z"]].to_numpy()
            if fmt == 3:
                y = (loser_sets == 0).astype(int)
                params[f"bo3_{who}_straight"] = _logistic(x, y)
            else:
                # best of five: the loser takes 0, 1 or 2 sets.
                y = np.asarray(loser_sets, dtype=int)
                model = LogisticRegression(C=100.0, max_iter=500)
                model.fit(x, y)
                params[f"bo5_{who}_split"] = {
                    "classes": [int(c) for c in model.classes_],
                    "intercept": [float(v) for v in model.intercept_],
                    "coef": [[float(v) for v in row] for row in model.coef_],
                }
    # --- first set: P(favourite wins set 1)
    params["set1_fav"] = _logistic(
        d[["z"]].to_numpy(), np.where(d["fav_is_home"], d["set1_home"], 1 - d["set1_home"])
    )
    # --- tiebreak anywhere in the match, and a first set that runs long
    x = _matrix(d)
    params["tiebreak"] = _logistic(x, d["tiebreak"].to_numpy())
    params["set1_over_9_5"] = _logistic(x, (d["set1_games"] > 9.5).astype(int).to_numpy())
    params["set1_over_10_5"] = _logistic(x, (d["set1_games"] > 10.5).astype(int).to_numpy())
    # --- margin in games: centre is proportional to the signed logit, spread by format
    margin = {}
    for fmt in (3, 5):
        g = d[d["best_of"] == fmt]
        sl = g["signed_logit"].to_numpy()
        slope = float(np.dot(sl, g["margin"]) / np.dot(sl, sl))
        resid = g["margin"] - slope * sl
        sd = float(np.std(resid))
        # The residual spread understates the tails (a claimed 65% cover happened 61%), so the
        # spread is the one at which the outer lines a bettor sees are most nearly honest on
        # these matches: smallest gap between claimed and happened, tried in steps of 0.1.
        mu_all = slope * sl
        best = (float("inf"), 1.0)
        for scale in np.arange(1.0, 1.81, 0.1):
            use = sd * float(scale)
            step = float(max(1, round(0.45 * use)))
            gap = 0.0
            for line in (-step, step):
                threshold = np.floor(mu_all) + 0.5 + line
                z_score = (mu_all - threshold) / use
                p_cover = 0.5 * np.vectorize(math.erfc)(-z_score / math.sqrt(2.0))
                happened = (g["margin"].to_numpy() > threshold).astype(float)
                gap += abs(float(np.mean(p_cover)) - float(np.mean(happened)))
            if gap < best[0] - 1e-9:
                best = (gap, float(scale))
        margin[f"bo{fmt}"] = {
            "slope": slope,
            "sd": sd * float(best[1]),
            "sd_scale": float(best[1]),
            "n": int(len(g)),
        }
    params["margin"] = margin
    params["fitted_on"] = {
        "matches": int(len(d)),
        "from": str(d["date"].min().date()),
        "to": str(d["date"].max().date()),
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    return params


# ---------------------------------------------------------------- evaluation


def evaluate(params: dict, test: pd.DataFrame) -> None:
    import ml.tennis_markets as tm

    tm.set_params(params)
    records = defaultdict(list)
    for r in test.itertuples():
        markets = tm.price_match(r.p_home, int(r.best_of), r.surface, r.tour)
        sets = r.sets
        home_sets, away_sets = int(r.home_sets), int(r.away_sets)
        for m in markets:
            graded = tm.grade_market(m, sets, home_sets, away_sets)
            if graded is None:
                continue
            kind = m["type"]
            if kind == "correct_score":
                for entry, res in zip(m["scores"], graded["scores"], strict=True):
                    records["set_score"].append((entry["prob"] / 100.0, res))
            elif kind == "over_under":
                for entry, res in zip(m["lines"], graded["lines"], strict=True):
                    records[m["id"]].append((entry["prob_over"] / 100.0, 1 if res == "over" else 0))
            elif kind == "handicap":
                for entry, res in zip(m["lines"], graded["lines"], strict=True):
                    records[m["id"]].append((entry["prob_home"] / 100.0, 1 if res == "home" else 0))
            elif kind == "two_way":
                records[m["id"]].append((m["home"] / 100.0, 1 if graded["result"] == "home" else 0))
            elif kind == "yes_no":
                records[m["id"]].append((m["yes"] / 100.0, 1 if graded["result"] == "yes" else 0))
    print(f"\nOut-of-sample calibration on {len(test)} matches since {CUT.date()}:")
    print(f"  {'market':<20}{'n':>8}{'brier':>8}{'base':>8}   claimed -> happened by band")
    bands = [(0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
    for key, rows in sorted(records.items()):
        p = np.array([r[0] for r in rows])
        y = np.array([r[1] for r in rows], dtype=float)
        brier = float(np.mean((p - y) ** 2))
        base = float(np.mean((y.mean() - y) ** 2))
        cells = []
        for lo, hi in bands:
            m = (p >= lo) & (p < hi)
            if m.sum() >= 40:
                cells.append(f"{p[m].mean() * 100:3.0f}->{y[m].mean() * 100:3.0f} ({int(m.sum())})")
        print(f"  {key:<20}{len(rows):>8}{brier:>8.4f}{base:>8.4f}   " + "  ".join(cells))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    d = prepare(with_probabilities(load_frame()))
    print(f"{len(d)} matches with set scores and two players with {MIN_PRIOR}+ prior matches")
    train, test = d[d["date"] < CUT], d[d["date"] >= CUT]
    print(f"train {len(train)} before {CUT.date()}, test {len(test)} after")
    evaluate(fit(train), test)
    final = fit(d)
    if not args.no_write:
        PARAMS_PATH.write_text(json.dumps(final, indent=1, sort_keys=True), encoding="utf-8")
        print(f"\nwrote {PARAMS_PATH}")


if __name__ == "__main__":
    main()
