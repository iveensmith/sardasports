"""Compare goal-model variants on held-out matches, as the live engine would have seen them.

For every sampled day from the start of the models' hold-out onward, each variant is fitted on
the history *before that day* (per fitting pool, exactly as `build_shared_fits` does) and
asked about the day's real matches. Reported per variant: log-loss for the match result, for
over 1.5 / 2.5 / 3.5 goals and for both teams to score, plus how often it claims home wins and
draws against how often they happened.

    python -m scripts.evaluate_goal_models run --shard 0 --of 4 --every 10
    python -m scripts.evaluate_goal_models report
"""

from __future__ import annotations

import argparse
import bisect
import csv
import glob
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from ml.competitions import fit_pool  # noqa: E402
from ml.poisson.model import DixonColesModel, PoissonModel  # noqa: E402

logger = logging.getLogger(__name__)
OUT_DIR = ROOT / "data" / "processed" / "calibration"
HOLD_OUT_FROM = datetime(2024, 9, 14)

VARIANTS = {
    "current": lambda day: PoissonModel(),
    "no_double_home": lambda day: PoissonModel(home_advantage=1.0),
    "dixon_coles": lambda day: DixonColesModel(),
    "dc_decay_0.002": lambda day: DixonColesModel(decay_per_day=0.002, as_of=day),
    "dc_decay_0.005": lambda day: DixonColesModel(decay_per_day=0.005, as_of=day),
    "dc_decay_0.001": lambda day: DixonColesModel(decay_per_day=0.001, as_of=day),
    "dc_decay_0.003": lambda day: DixonColesModel(decay_per_day=0.003, as_of=day),
}


def _load_history() -> list[dict]:
    from app.database.session import SessionLocal
    from app.services import prediction_service as ps

    session = SessionLocal()
    try:
        rows = ps._all_completed_history(session, datetime(2100, 1, 1), "football")
    finally:
        session.close()
    rows = [r for r in rows if r.get("home_score") is not None and r.get("away_score") is not None]
    rows.sort(key=lambda r: r["match_date"])
    return list(rows)


def run(shard: int, of: int, every: int, only: list[str] | None = None) -> None:
    history = _load_history()
    dates = [r["match_date"] for r in history]
    start = bisect.bisect_left(dates, HOLD_OUT_FROM)
    days = sorted({d.date() for d in dates[start:]})
    mine = [d for i, d in enumerate(days) if i % every == 0 and (i // every) % of == shard]
    logger.info("shard %d/%d: %d of %d days", shard, of, len(mine), len(days))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = "_" + "+".join(only) if only else ""
    path = OUT_DIR / f"goal_models{tag}_{shard}_of_{of}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["variant", "date", "competition", "home_score", "away_score"]
            + ["p_h", "p_d", "p_a", "p_o15", "p_o25", "p_o35", "p_btts", "rho"]
        )
        for index, day in enumerate(mine):
            day_start = datetime.combine(day, datetime.min.time())
            cut = bisect.bisect_left(dates, day_start)
            end = bisect.bisect_left(dates, day_start + timedelta(days=1))
            today = history[cut:end]
            by_pool: dict[str | None, list[dict]] = {}
            for match in today:
                by_pool.setdefault(fit_pool(match.get("competition")), []).append(match)
            past = history[:cut]
            for pool, fixtures in by_pool.items():
                scoped = [m for m in past if fit_pool(m.get("competition")) == pool]
                if len(scoped) < 100:
                    continue
                fit_rows = [
                    {
                        "home_team": m["home_team"],
                        "away_team": m["away_team"],
                        "home_score": m["home_score"],
                        "away_score": m["away_score"],
                        "match_date": m["match_date"],
                    }
                    for m in scoped
                ]
                for name, factory in VARIANTS.items():
                    if only and name not in only:
                        continue
                    model = factory(day_start).fit(fit_rows)
                    for fx in fixtures:
                        h, a = fx["home_team"], fx["away_team"]
                        ph, pd_, pa = model.result_probabilities(h, a)
                        matrix = model.scoreline_matrix(h, a)
                        size = matrix.shape[0]
                        totals = np.add.outer(np.arange(size), np.arange(size))
                        writer.writerow(
                            [
                                name,
                                fx["match_date"].isoformat(),
                                fx.get("competition"),
                                fx["home_score"],
                                fx["away_score"],
                                f"{ph:.5f}",
                                f"{pd_:.5f}",
                                f"{pa:.5f}",
                                f"{matrix[totals > 1.5].sum():.5f}",
                                f"{matrix[totals > 2.5].sum():.5f}",
                                f"{matrix[totals > 3.5].sum():.5f}",
                                f"{matrix[1:, 1:].sum():.5f}",
                                f"{getattr(model, 'rho', 0.0):.4f}",
                            ]
                        )
            if index % 5 == 0:
                logger.info("shard %d: day %d/%d", shard, index + 1, len(mine))
                handle.flush()
    logger.info("wrote %s", path)


def _ll(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def report() -> None:
    import pandas as pd

    files = sorted(glob.glob(str(OUT_DIR / "goal_models*_of_*.csv")))
    data = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    n_matches = len(data[data["variant"] == "current"])
    print(f"{n_matches} held-out matches, {data['date'].min()[:10]} .. {data['date'].max()[:10]}\n")
    header = (
        f"{'variant':<16}{'1X2 logloss':>12}{'acc':>7}{'home':>8}{'draw':>8}"
        f"{'o1.5':>8}{'o2.5':>8}{'o3.5':>8}{'btts':>8}{'rho':>8}"
    )
    print(header)
    for name, g in data.groupby("variant", sort=False):
        hs, as_ = g["home_score"].to_numpy(), g["away_score"].to_numpy()
        outcome = np.where(hs > as_, 0, np.where(hs == as_, 1, 2))
        probs = g[["p_h", "p_d", "p_a"]].to_numpy()
        ll = float(-np.mean(np.log(np.clip(probs[np.arange(len(g)), outcome], 1e-6, 1))))
        acc = float(np.mean(np.argmax(probs, axis=1) == outcome))
        total = hs + as_
        row = [
            ll,
            acc,
            float(g["p_h"].mean()),
            float(g["p_d"].mean()),
            _ll(g["p_o15"].to_numpy(), (total > 1.5).astype(float)),
            _ll(g["p_o25"].to_numpy(), (total > 2.5).astype(float)),
            _ll(g["p_o35"].to_numpy(), (total > 3.5).astype(float)),
            _ll(g["p_btts"].to_numpy(), ((hs > 0) & (as_ > 0)).astype(float)),
            float(g["rho"].mean()),
        ]
        print(
            f"{name:<16}{row[0]:>12.4f}{row[1]:>7.3f}{row[2]:>8.3f}{row[3]:>8.3f}"
            f"{row[4]:>8.4f}{row[5]:>8.4f}{row[6]:>8.4f}{row[7]:>8.4f}{row[8]:>8.3f}"
        )
    any_variant = data[data["variant"] == "current"]
    hs, as_ = any_variant["home_score"].to_numpy(), any_variant["away_score"].to_numpy()
    print(
        f"\nactual: home {np.mean(hs > as_):.3f}  draw {np.mean(hs == as_):.3f}  "
        f"over1.5 {np.mean(hs + as_ > 1.5):.3f}  over2.5 {np.mean(hs + as_ > 2.5):.3f}  "
        f"over3.5 {np.mean(hs + as_ > 3.5):.3f}  btts {np.mean((hs > 0) & (as_ > 0)):.3f}"
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--shard", type=int, default=0)
    r.add_argument("--of", type=int, default=1)
    r.add_argument("--every", type=int, default=10, help="use every Nth day")
    r.add_argument("--only", default="", help="comma-separated variant names")
    sub.add_parser("report")
    args = parser.parse_args()
    if args.command == "run":
        run(args.shard, args.of, args.every, [v for v in args.only.split(",") if v] or None)
    else:
        report()


if __name__ == "__main__":
    main()
