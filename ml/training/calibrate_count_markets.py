"""Calibrate the corner and card probabilities.

Why this exists
---------------
Graded against what actually happened, the engine's corner and card lines run about five
points too confident: a corner call claiming a 5-point lift over its league's base rate
realised 2.4, and a card call claiming 6.8 realised 4.8, while match-result, goals and
double-chance calls realised what they claimed. The headline had to be held to a higher
bar for those two markets as a stopgap. This fixes the probabilities themselves.

How
---
1. **Replay.** The active corner and card models were trained on matches before about
   September 2024 and have never seen the matches after it. So replaying the engine over
   that later stretch, one day at a time with the history cut at the start of each day,
   gives honest out-of-sample probabilities for the *blended* number the site actually shows
   (dedicated model weighted with the Poisson baseline), not for the dedicated model alone.
   Each shard replays a share of the days (`--shard k --of n`) so several processes can run
   at once; the output is one CSV per shard.
2. **Fit.** For each market and line, a logistic (Platt) curve is fitted from the blended
   probability to whether the line was beaten: `p' = sigmoid(slope * logit(p) + intercept)`.
   A slope under 1 pulls an overconfident probability back towards the middle. The curve is
   fitted on the earlier 60% of the replayed matches and scored on the later 40%, and the
   report shows log-loss, Brier score and a reliability table before and after. Only if it
   helps on matches it was not fitted on is it registered; it is then refitted on everything.
3. **Apply.** The curves are stored as `calibration_<market>_over_<line>` rows in the model
   registry. `app.services.prediction_service` applies them to the corner and card lines of
   every football prediction made afterwards. A prediction already stored before its match
   started is final and is not rewritten.

Usage:
    python -m ml.training.calibrate_count_markets replay --shard 0 --of 6
    python -m ml.training.calibrate_count_markets fit
"""

from __future__ import annotations

import argparse
import logging
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from app.database.session import SessionLocal
from app.models import Match
from ml.training.common import new_version_string, register_model_version

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "calibration"
# The models never saw anything after this date (the start of their 20% hold-out).
HOLD_OUT_FROM = datetime(2024, 9, 14)
MARKETS = ("corners", "cards")
FIT_FRACTION = 0.6
MIN_POINTS = 800
# A curve is only worth registering if it beats the raw probabilities on held-back matches by
# more than noise: an improvement of a few ten-thousandths of a log-loss unit is not evidence.
MIN_IMPROVEMENT = 0.0005
EPS = 1e-4


def _logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def apply_curve(p: float, slope: float, intercept: float) -> float:
    """The calibrated probability for a raw one."""
    z = slope * math.log(min(max(p, EPS), 1 - EPS) / (1 - min(max(p, EPS), 1 - EPS))) + intercept
    return 1.0 / (1.0 + math.exp(-z))


def model_name(market: str, line: float) -> str:
    return f"calibration_{market}_over_{str(line).replace('.', '_')}"


# --- replay -------------------------------------------------------------------------------------


def replay(shard: int, of: int, every: int = 1) -> None:
    from app.services import prediction_service as ps
    from app.services.elo_service import get_team_elo_before
    from app.utils.config import get_settings
    from ml.prediction.predict import CARDS_LINES, CORNERS_LINES, predict_match

    settings = get_settings()
    session = SessionLocal()
    try:
        rows = (
            session.query(Match)
            .filter(
                Match.sport == "football",
                Match.status == "completed",
                Match.match_date >= HOLD_OUT_FROM,
                Match.home_score.is_not(None),
            )
            .order_by(Match.match_date.asc())
            .all()
        )

        def corners(m):
            if m.home_corners is None or m.away_corners is None:
                return None
            return m.home_corners + m.away_corners

        def cards(m):
            parts = (m.home_yellow_cards, m.away_yellow_cards, m.home_red_cards, m.away_red_cards)
            return None if any(p is None for p in parts) else sum(parts)

        wanted = [m for m in rows if corners(m) is not None or cards(m) is not None]
        by_day: dict = {}
        for m in wanted:
            by_day.setdefault(m.match_date.date(), []).append(m)
        days = sorted(by_day)
        mine = [d for i, d in enumerate(days) if i % every == 0 and (i // every) % of == shard]
        logger.info("shard %d/%d: %d of %d days", shard, of, len(mine), len(days))

        def load(lines, name_for_line, loader):
            out = {}
            for line in lines:
                model, scaler, _v = ps._get_active_model(session, name_for_line(line), loader)
                if model is not None:
                    out[line] = (model, scaler)
            return out

        xgb_model, xgb_scaler, _ = ps._get_active_model(
            session, ps.MATCH_RESULT_MODEL_NAME, ps._load_xgboost_cached
        )
        btts_model, btts_scaler, _ = ps._get_active_model(
            session, ps.BTTS_MODEL_NAME, ps._load_sklearn_pickle_cached
        )
        goals_models = load(ps.GOALS_LINES, ps.goals_model_name_for_line, ps._load_lightgbm_cached)
        ht_models = load(
            ps.HT_GOALS_LINES, ps.ht_goals_model_name_for_line, ps._load_lightgbm_cached
        )
        corner_models = load(
            CORNERS_LINES, ps.corners_model_name_for_line, ps._load_lightgbm_cached
        )
        card_models = load(
            CARDS_LINES, ps.cards_model_name_for_line, ps._load_sklearn_pickle_cached
        )

        names = {t.id: t.name for t in session.query(ps.Team).filter(ps.Team.sport == "football")}
        out = []
        for index, day in enumerate(mine):
            start = datetime.combine(day, datetime.min.time())
            window = ps._all_completed_history(session, start, "football")
            matches = by_day[day]
            shared = ps._shared_fits_for(window, sorted({m.competition for m in matches}, key=str))
            for m in matches:
                try:
                    result = predict_match(
                        home_team=names[m.home_team_id],
                        away_team=names[m.away_team_id],
                        match_date=m.match_date,
                        history=window,
                        elo_home=get_team_elo_before(session, m.home_team_id, m.match_date),
                        elo_away=get_team_elo_before(session, m.away_team_id, m.match_date),
                        elo_k_factor=settings.elo_k_factor,
                        elo_home_advantage=settings.elo_home_advantage,
                        competition=m.competition,
                        xgb_model=xgb_model,
                        xgb_scaler_params=xgb_scaler,
                        btts_model=btts_model,
                        btts_scaler_params=btts_scaler,
                        goals_models=goals_models,
                        ht_goals_models=ht_models,
                        corners_models=corner_models,
                        cards_models=card_models,
                        shared=shared.get(m.competition),
                    )
                except Exception as exc:  # noqa: BLE001 - one bad fixture must not stop a replay
                    logger.warning("match %s skipped: %s", m.id, exc)
                    continue
                for market, total, entries in (
                    ("corners", corners(m), result.corners_markets),
                    ("cards", cards(m), result.cards_markets),
                ):
                    if total is None:
                        continue
                    for entry in entries or []:
                        if entry.get("prob_over") is None:
                            continue
                        out.append(
                            (
                                market,
                                entry["line"],
                                m.competition,
                                m.match_date.isoformat(),
                                entry["prob_over"] / 100.0,
                                int(total > entry["line"]),
                                int(bool(entry.get("model_used"))),
                            )
                        )
            if index % 20 == 0:
                logger.info(
                    "shard %d: %d/%d days, %d points", shard, index + 1, len(mine), len(out)
                )
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUT_DIR / f"replay_{shard}_of_{of}.csv"
        pd.DataFrame(
            out, columns=["market", "line", "competition", "date", "p", "y", "model_used"]
        ).to_csv(path, index=False)
        logger.info("wrote %s (%d rows)", path, len(out))
    finally:
        session.close()


# --- fit ----------------------------------------------------------------------------------------


def _scores(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return {
        "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        "brier": float(np.mean((p - y) ** 2)),
    }


def _reliability(p, y, bins=(0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 1.01)):
    rows = []
    for low, high in zip(bins[:-1], bins[1:], strict=True):
        mask = (p >= low) & (p < high)
        if mask.sum() >= 30:
            rows.append((low, high, int(mask.sum()), float(p[mask].mean()), float(y[mask].mean())))
    return rows


def _fit_curve(p, y):
    model = LogisticRegression(C=1e6, max_iter=1000)
    model.fit(_logit(p).reshape(-1, 1), y)
    return float(model.coef_[0][0]), float(model.intercept_[0])


def fit(register: bool = True) -> None:
    frames = [pd.read_csv(path) for path in sorted(OUT_DIR.glob("replay_*_of_*.csv"))]
    if not frames:
        raise SystemExit("No replay files found; run `replay` first.")
    data = pd.concat(frames).sort_values("date").reset_index(drop=True)
    logger.info("%d replayed points", len(data))

    version = new_version_string()
    for market in MARKETS:
        for line in sorted(data[data["market"] == market]["line"].unique()):
            part = data[(data["market"] == market) & (data["line"] == line)]
            if len(part) < MIN_POINTS:
                logger.warning("%s %s: only %d points, skipped", market, line, len(part))
                continue
            cut = int(len(part) * FIT_FRACTION)
            early, late = part.iloc[:cut], part.iloc[cut:]
            slope, intercept = _fit_curve(early["p"].to_numpy(), early["y"].to_numpy())
            p_late = late["p"].to_numpy()
            y_late = late["y"].to_numpy()
            calibrated = np.array([apply_curve(p, slope, intercept) for p in p_late])
            before, after = _scores(p_late, y_late), _scores(calibrated, y_late)
            print(
                f"\n=== {market} over {line}: {len(part)} points, "
                f"fitted on {cut}, tested on {len(late)}"
            )
            print(f"  curve: slope {slope:.3f}, intercept {intercept:+.3f}")
            print(f"  log-loss {before['log_loss']:.4f} -> {after['log_loss']:.4f}")
            print(f"  brier    {before['brier']:.4f} -> {after['brier']:.4f}")
            print("  reliability on the held-back 40% (raw / calibrated / actual):")
            raw_rel = {r[0]: r for r in _reliability(p_late, y_late)}
            cal_rel = {r[0]: r for r in _reliability(calibrated, y_late)}
            for low, row in raw_rel.items():
                cal = cal_rel.get(low)
                print(
                    f"    {low:.1f}-{row[1]:.1f}  n={row[2]:4d}  raw {row[3]:.3f}"
                    f"  cal {cal[3] if cal else float('nan'):.3f}  actual {row[4]:.3f}"
                )
            helps = (
                before["log_loss"] - after["log_loss"] >= MIN_IMPROVEMENT
                and after["brier"] < before["brier"]
            )
            if not helps:
                print("  -> does not help on held-back matches; not registered")
                continue
            if register:
                slope, intercept = _fit_curve(part["p"].to_numpy(), part["y"].to_numpy())
                metrics = {
                    "market": market,
                    "line": float(line),
                    "slope": slope,
                    "intercept": intercept,
                    "num_points": int(len(part)),
                    "log_loss_before": before["log_loss"],
                    "log_loss_after": after["log_loss"],
                    "brier_before": before["brier"],
                    "brier_after": after["brier"],
                }
                register_model_version(
                    model_name(market, float(line)),
                    version,
                    "n/a (calibration curve)",
                    metrics,
                    int(len(part)),
                )
                print(f"  -> registered {model_name(market, float(line))}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--shard", type=int, default=0)
    r.add_argument("--of", type=int, default=1)
    r.add_argument("--every", type=int, default=1, help="use every Nth day")
    f = sub.add_parser("fit")
    f.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    if args.command == "replay":
        replay(args.shard, args.of, args.every)
    else:
        fit(register=not args.no_register)


if __name__ == "__main__":
    main()
