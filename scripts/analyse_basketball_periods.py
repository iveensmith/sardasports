"""Research for the basketball period markets: structure, then out-of-sample accuracy.

For every finished game with quarter scores, builds the same pre-game estimate the live engine
uses (`ml.prediction.predict_basketball`: what each side scores blended with what the other
concedes, from prior games only), then asks how a quarter, a half, a team's points and the
margin behave around it. Fitted on games before the cut and scored on games after, so every
figure is out of sample.

    python -m scripts.analyse_basketball_periods
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.database.session import SessionLocal  # noqa: E402
from app.models.match import Match  # noqa: E402
from app.models.team import Team  # noqa: E402
from app.utils.config import get_settings  # noqa: E402
from ml.training.basketball_common import build_feature_frame  # noqa: E402

CUT = datetime(2024, 9, 1)


def load_games() -> list[dict]:
    session = SessionLocal()
    try:
        names = {t.id: t.name for t in session.query(Team).filter(Team.sport == "basketball")}
        games = []
        for m in (
            session.query(Match)
            .filter(Match.sport == "basketball", Match.status == "completed")
            .order_by(Match.match_date.asc(), Match.id.asc())
        ):
            periods = m.period_scores
            if isinstance(periods, str):
                periods = json.loads(periods)
            games.append(
                {
                    "match_id": m.id,
                    "match_date": m.match_date,
                    "competition": m.competition,
                    "season": m.season,
                    "home_team": names.get(m.home_team_id, ""),
                    "away_team": names.get(m.away_team_id, ""),
                    "home_score": m.home_score,
                    "away_score": m.away_score,
                    "periods": periods,
                }
            )
        return games
    finally:
        session.close()


def main() -> None:
    games = load_games()
    print(f"{len(games)} finished games; {sum(1 for g in games if g['periods'])} with quarters")
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
        row = {
            "date": g["match_date"],
            "competition": g["competition"],
            "eh": eh,
            "ea": ea,
            "elo_diff": rec["elo_diff"],
            "home_final": g["home_score"],
            "away_final": g["away_score"],
        }
        for i in range(4):
            row[f"h{i + 1}"] = p["home"][i]
            row[f"a{i + 1}"] = p["away"][i]
        row["ot"] = 1 if p.get("ot") else 0
        rows.append(row)
    df = pd.DataFrame(rows)
    df["home_reg"] = df[["h1", "h2", "h3", "h4"]].sum(axis=1)
    df["away_reg"] = df[["a1", "a2", "a3", "a4"]].sum(axis=1)
    df["total_reg"] = df["home_reg"] + df["away_reg"]
    for i in range(1, 5):
        df[f"t{i}"] = df[f"h{i}"] + df[f"a{i}"]
    df["h1_total"] = df["t1"] + df["t2"]
    df["h2_total"] = df["t3"] + df["t4"]
    df["exp_total"] = df["eh"] + df["ea"]
    print(f"{len(df)} games with a pre-game estimate and quarters\n")

    print("Points per quarter (mean), and Q3+Q4 as a share of regulation, by league:")
    big = df.groupby("competition").filter(lambda g: len(g) >= 300)
    for comp, g in big.groupby("competition"):
        q = [g[f"t{i}"].mean() for i in range(1, 5)]
        print(
            f"  {comp:<32} n={len(g):>5}  Q1 {q[0]:6.1f}  Q2 {q[1]:6.1f}  Q3 {q[2]:6.1f}"
            f"  Q4 {q[3]:6.1f}"
            f"   reg total {g['total_reg'].mean():6.1f}   exp {g['exp_total'].mean():6.1f}"
            f"   OT {100 * g['ot'].mean():4.1f}%"
        )

    train = df[df["date"] < CUT]
    test = df[df["date"] >= CUT]
    print(f"\ntrain {len(train)} games before {CUT.date()}, test {len(test)} after\n")

    # How much better than the league's own average is the pre-game estimate? (period totals)
    print("Out-of-sample error of a period total (mean absolute error, points):")
    print(f"  {'period':<14}{'league avg':>12}{'estimate x share':>18}")
    for label, col in (
        ("game (reg.)", "total_reg"),
        ("1st half", "h1_total"),
        ("2nd half", "h2_total"),
        ("quarter 1", "t1"),
        ("quarter 2", "t2"),
        ("quarter 3", "t3"),
        ("quarter 4", "t4"),
    ):
        base_err = []
        est_err = []
        league_mean = train.groupby("competition")[col].mean()
        league_total_share = (train[col] / train["total_reg"]).groupby(train["competition"]).mean()
        league_bias = (train["total_reg"] / train["exp_total"]).groupby(train["competition"]).mean()
        for comp, g in test.groupby("competition"):
            if comp not in league_mean.index:
                continue
            base = league_mean[comp]
            est = g["exp_total"] * league_bias[comp] * league_total_share[comp]
            base_err.extend(abs(g[col] - base))
            est_err.extend(abs(g[col] - est))
        print(f"  {label:<14}{np.mean(base_err):>12.2f}{np.mean(est_err):>18.2f}")


if __name__ == "__main__":
    main()
