"""Fit the basketball period profiles, and report how well they price games they never saw.

Writes `ml/basketball_period_profiles.json` (read by `ml/basketball_markets.py`). The profile
for a league and format holds: how a game's points split across periods, how far a period's
points stray from that split (as a share of the expectation, so it scales across leagues),
and the spread of a period's margin.

    python -m scripts.fit_basketball_period_profiles            # evaluate, then write
    python -m scripts.fit_basketball_period_profiles --no-write

Evaluation: fit on games before CUT, price every game after it with the production
`price_game`, and compare each stated probability with what happened.
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

import ml.basketball_markets as bm  # noqa: E402
from ml.elo.engine import EloEngine  # noqa: E402
from scripts.analyse_basketball_periods import CUT, load_games  # noqa: E402

MIN_FIT_GAMES = bm.MIN_LEAGUE_GAMES
SLOPE_FROM = datetime(2024, 1, 1)
ORIGINAL_LOAD_PROFILES = bm.load_profiles


def build_frame() -> pd.DataFrame:
    from app.utils.config import get_settings
    from ml.training.basketball_common import build_feature_frame

    games = load_games()
    frame = build_feature_frame(
        [{k: v for k, v in g.items() if k != "periods"} for g in games], get_settings()
    )
    by_id = {g["match_id"]: g for g in games}
    rows = []
    for rec in frame.to_dict("records"):
        g = by_id[rec["match_id"]]
        p = g["periods"]
        if not p:
            continue

        def expected(scored, conceded):
            parts = [x for x in (scored, conceded) if x and x > 0]
            return sum(parts) / len(parts) if parts else float("nan")

        eh = expected(rec["home_avg_points_scored"], rec["away_avg_points_conceded"])
        ea = expected(rec["away_avg_points_scored"], rec["home_avg_points_conceded"])
        if not (eh == eh and ea == ea):
            continue
        ot = p.get("ot") or [0, 0]
        row = {
            "date": g["match_date"],
            "competition": g["competition"],
            "eh": eh,
            "ea": ea,
            "elo_home": rec["elo_home"],
            "elo_away": rec["elo_away"],
            "home_final": g["home_score"],
            "away_final": g["away_score"],
            "home_ot": ot[0],
            "away_ot": ot[1],
        }
        for i in range(4):
            row[f"h{i + 1}"] = p["home"][i]
            row[f"a{i + 1}"] = p["away"][i]
        rows.append(row)
    df = pd.DataFrame(rows)
    df["format"] = np.where(
        (df["h1"] + df["a1"] == 0) & (df["h3"] + df["a3"] == 0), "halves", "quarters"
    )
    for i in range(1, 5):
        df[f"t{i}"] = df[f"h{i}"] + df[f"a{i}"]
        df[f"m{i}"] = df[f"h{i}"] - df[f"a{i}"]
    df["total_reg"] = df[["t1", "t2", "t3", "t4"]].sum(axis=1)
    df["home_reg"] = df[["h1", "h2", "h3", "h4"]].sum(axis=1)
    df["away_reg"] = df[["a1", "a2", "a3", "a4"]].sum(axis=1)
    df["exp_total"] = df["eh"] + df["ea"]
    df["margin_final"] = df["home_final"] - df["away_final"]
    # Halves: the source records them in slots 2 and 4.
    half = df["format"] == "halves"
    df["th1"] = np.where(half, df["t2"], df["t1"] + df["t2"])
    df["th2"] = np.where(half, df["t4"], df["t3"] + df["t4"])
    df["mh1"] = np.where(half, df["m2"], df["m1"] + df["m2"])
    df["mh2"] = np.where(half, df["m4"], df["m3"] + df["m4"])
    df["win_p"] = [
        EloEngine.expected_score(h + 60.0, a)
        for h, a in zip(df["elo_home"], df["elo_away"], strict=True)
    ]
    return df


def _profile(g: pd.DataFrame, fmt: str) -> dict:
    exp_total = g["exp_total"]
    bias_total = g["total_reg"].sum() / exp_total.sum()
    bias_home = g["home_final"].sum() / g["eh"].sum()
    bias_away = g["away_final"].sum() / g["ea"].sum()
    mean_pred_total = exp_total * bias_total

    # Pre-game expected margin: regression of the final margin on what the pre-game numbers know.
    x = np.column_stack([np.ones(len(g)), g["elo_home"] - g["elo_away"], g["eh"] - g["ea"]])
    coef, *_ = np.linalg.lstsq(x, g["margin_final"].to_numpy(), rcond=None)
    margin_pred = x @ coef
    avg_total = float(mean_pred_total.mean())

    def cv_of(col: str, mean_pred: pd.Series) -> float:
        resid = g[col] - mean_pred
        return float(np.std(resid) / max(float(mean_pred.mean()), 1e-9))

    periods = ("q1", "q2", "q3", "q4") if fmt == "quarters" else ()
    shares = {}
    cv = {
        "total": cv_of("total_reg", mean_pred_total),
        "home": cv_of("home_final", g["eh"] * bias_home),
        "away": cv_of("away_final", g["ea"] * bias_away),
    }
    margin_ratio = {}
    full_resid = g["margin_final"] - margin_pred
    margin_ratio["full"] = float(np.std(full_resid) / avg_total)
    for p in periods:
        col = "t" + p[1]
        share = g[col].sum() / g["total_reg"].sum()
        shares[p] = float(share)
        cv[p] = cv_of(col, mean_pred_total * share)
        margin_ratio[p] = float(np.std(g["m" + p[1]] - share * margin_pred) / avg_total)
    for h in ("h1", "h2"):
        col = "t" + h
        share = g[col].sum() / g["total_reg"].sum()
        shares[h] = float(share)
        cv[h] = cv_of(col, mean_pred_total * share)
        margin_ratio[h] = float(np.std(g["m" + h] - share * margin_pred) / avg_total)
    return {
        "n": int(len(g)),
        "bias": {"total": float(bias_total), "home": float(bias_home), "away": float(bias_away)},
        "shares": shares,
        "cv": cv,
        "margin_sd_ratio": margin_ratio,
    }


def fit(df: pd.DataFrame) -> dict:
    out = {"leagues": {}, "default": {}}
    for fmt in ("quarters", "halves"):
        pool = df[df["format"] == fmt]
        if len(pool) >= MIN_FIT_GAMES:
            out["default"][fmt] = _profile(pool, fmt)
    for (comp, fmt), g in df.groupby(["competition", "format"]):
        if len(g) >= MIN_FIT_GAMES:
            out["leagues"].setdefault(comp, {})[fmt] = _profile(g, fmt)
    out["fitted_on"] = {
        "games": int(len(df)),
        "from": str(df["date"].min().date()),
        "to": str(df["date"].max().date()),
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    return out


# ---------------------------------------------------------------- evaluation


def fit_winner_slope(profiles: dict, games: pd.DataFrame) -> float:
    """Logistic slope of what happened on what the winner markets said, on `games`.

    A slope under 1 means the period winners were overconfident and are pulled towards even.
    """
    from sklearn.linear_model import LogisticRegression

    previous = ORIGINAL_LOAD_PROFILES
    bm.load_profiles = lambda: {**profiles, "winner_slope": 1.0}  # type: ignore[assignment]
    xs, ys = [], []
    try:
        for rec in games.to_dict("records"):
            priced = bm.price_game(rec["eh"], rec["ea"], rec["win_p"], rec["competition"])
            periods = {
                "home": [rec["h1"], rec["h2"], rec["h3"], rec["h4"]],
                "away": [rec["a1"], rec["a2"], rec["a3"], rec["a4"]],
                "ot": None,
            }
            for market in priced:
                if market["type"] != "three_way":
                    continue
                graded = bm.grade_market(market, periods, None)
                if graded is None or graded["result"] == "tie":
                    continue
                home, away = market["home"] / 100.0, market["away"] / 100.0
                conditional = min(max(home / (home + away), 1e-3), 1 - 1e-3)
                xs.append(math.log(conditional / (1 - conditional)))
                ys.append(1 if graded["result"] == "home" else 0)
    finally:
        bm.load_profiles = previous
    model = LogisticRegression(C=1e6, fit_intercept=False)
    model.fit(np.array(xs).reshape(-1, 1), np.array(ys))
    return float(model.coef_[0][0])


def evaluate(profiles: dict, test: pd.DataFrame) -> None:
    bm.load_profiles = lambda: profiles  # type: ignore[assignment]
    records = defaultdict(list)  # group -> [(p, outcome)]
    for rec in test.to_dict("records"):
        priced = bm.price_game(rec["eh"], rec["ea"], rec["win_p"], rec["competition"])
        if not priced:
            continue
        periods = {
            "home": [rec["h1"], rec["h2"], rec["h3"], rec["h4"]],
            "away": [rec["a1"], rec["a2"], rec["a3"], rec["a4"]],
            "ot": [rec["home_ot"], rec["away_ot"]] if rec["home_ot"] or rec["away_ot"] else None,
        }
        final = (rec["home_final"], rec["away_final"])
        for market in priced:
            graded = bm.grade_market(market, periods, final)
            if graded is None:
                continue
            group = market["id"].split("_")[0] if market["id"] != "spread" else "spread"
            if market["id"].startswith("team_total"):
                group = "team_total"
            elif market["id"].endswith("_total") and market["id"][0] in "qh":
                group = "half_total" if market["id"][0] == "h" else "quarter_total"
            elif market["id"].endswith("_winner"):
                group = "half_winner" if market["id"][0] == "h" else "quarter_winner"
            if market["type"] == "over_under":
                for line, res in zip(market["lines"], graded["lines"], strict=True):
                    records[group].append(
                        (line["prob_over"] / 100.0, 1 if res == "over" else 0)
                    )
            elif market["type"] == "handicap":
                for line, res in zip(market["lines"], graded["lines"], strict=True):
                    records[group].append(
                        (line["prob_home"] / 100.0, 1 if res == "home" else 0)
                    )
            elif market["type"] == "three_way":
                records[group].append(
                    (market["home"] / 100.0, 1 if graded["result"] == "home" else 0)
                )
                records[group].append(
                    (market["away"] / 100.0, 1 if graded["result"] == "away" else 0)
                )
                records[group + "_tie"].append(
                    (market["tie"] / 100.0, 1 if graded["result"] == "tie" else 0)
                )
    print(f"\nOut-of-sample calibration on {len(test)} games after {CUT.date()}:")
    print(f"  {'market group':<16}{'n':>8}{'brier':>8}{'vs 50%':>8}   claimed -> happened by band")
    bands = [(0, 0.25), (0.25, 0.4), (0.4, 0.6), (0.6, 0.75), (0.75, 1.01)]
    for group, rows in sorted(records.items()):
        p = np.array([r[0] for r in rows])
        y = np.array([r[1] for r in rows])
        brier = float(np.mean((p - y) ** 2))
        base = (
            float(np.mean((0.5 - y) ** 2))
            if not group.endswith("_tie")
            else float(np.mean((y.mean() - y) ** 2))
        )
        cells = []
        for lo, hi in bands:
            m = (p >= lo) & (p < hi)
            if m.sum() >= 30:
                cells.append(f"{p[m].mean() * 100:4.0f}->{y[m].mean() * 100:4.0f} ({int(m.sum())})")
        print(f"  {group:<16}{len(rows):>8}{brier:>8.4f}{base:>8.4f}   " + "  ".join(cells))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    df = build_frame()
    print(f"{len(df)} games with quarters and a pre-game estimate; "
          f"{(df['format'] == 'halves').sum()} recorded in halves")  # fmt: skip
    train, test = df[df["date"] < CUT], df[df["date"] >= CUT]
    trained = fit(train)
    # Fitted on the most recent training games only: early on, ratings are immature and rarely
    # extreme, which hides the overconfidence a settled league shows.
    recent = train[train["date"] >= SLOPE_FROM]
    trained["winner_slope"] = fit_winner_slope(trained, recent)
    print(
        f"winner slope fitted on {len(recent)} training games since {SLOPE_FROM.date()}: "
        f"{trained['winner_slope']:.3f}"
    )
    evaluate(trained, test)
    print(
        "\nfor reference, the slope the later games alone would have asked for: "
        f"{fit_winner_slope(trained, test):.3f}"
    )
    final = fit(df)
    mature = df[df["date"] >= SLOPE_FROM]
    final["winner_slope"] = fit_winner_slope(final, mature)
    if not args.no_write:
        bm.PROFILE_PATH.write_text(json.dumps(final, indent=1, sort_keys=True), encoding="utf-8")
        print(f"\nwrote {bm.PROFILE_PATH} ({len(final['leagues'])} leagues)")


if __name__ == "__main__":
    main()
