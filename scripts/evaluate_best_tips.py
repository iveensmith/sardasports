"""The full engine, end to end, on held-out matches: how often do its best tips win?

`evaluate_goal_models` scores one component. This runs everything the live engine runs
(Elo, the goals model, XGBoost, the dedicated goals/BTTS/corners/cards models, the
read-time corner curves and match-result correction), chooses each fixture's best tip with the
production rules and grades it against the real result, for either goals model:

    python -m scripts.evaluate_best_tips run --variant new --shard 0 --of 4 --every 3
    python -m scripts.evaluate_best_tips run --variant old --shard 0 --of 4 --every 3
    python -m scripts.evaluate_best_tips report

`old` is the plain `PoissonModel` (with its double-counted home advantage) and the registered
match-result correction that was fitted to it; `new` is the Dixon-Coles model, which needs no
correction. Both use the same matches, the same history cut at the start of each day and the same
best-tip rules, so the difference is the goals model alone.
"""

from __future__ import annotations

import argparse
import csv
import glob
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)
OUT_DIR = ROOT / "data" / "processed" / "calibration"
HOLD_OUT_FROM = datetime(2024, 9, 14)
# The correction fitted to the plain Poisson blend (ml.training.calibrate_match_result).
OLD_RESULT_CORRECTION = (1.064, -0.091, 0.092)


def _old_goals_model(matches: list[dict]):
    from ml.poisson.model import PoissonModel

    return PoissonModel().fit(matches) if matches else PoissonModel()


def run(variant: str, shard: int, of: int, every: int) -> None:
    from app.database.session import SessionLocal
    from app.models import Match
    from app.services import prediction_service as ps
    from app.services.base_rates import competition_base_rates
    from app.services.count_calibration import calibrate_payload
    from app.services.elo_service import get_team_elo_before
    from app.services.settlement import result_from_match, settle_key
    from app.utils.config import get_settings
    from ml.markets import candidate_calls, headline_call, rank_calls
    from ml.prediction import predict as predict_module
    from ml.prediction.predict import (
        CARDS_LINES,
        CORNERS_LINES,
        predict_match,
    )
    from ml.training.calibrate_match_result import apply_result_calibration

    if variant == "old":
        # build_shared_fits looks this name up when it runs, so the swap takes effect.
        predict_module.fit_goals_model = _old_goals_model

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
        by_day: dict = {}
        for m in rows:
            by_day.setdefault(m.match_date.date(), []).append(m)
        days = sorted(by_day)
        mine = [d for i, d in enumerate(days) if i % every == 0 and (i // every) % of == shard]
        logger.info("%s shard %d/%d: %d of %d days", variant, shard, of, len(mine), len(days))

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

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUT_DIR / f"best_tips_{variant}_{shard}_of_{of}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["variant", "match_id", "date", "competition", "key", "market",
                             "probability", "outcome", "strong"])  # fmt: skip
            for index, day in enumerate(mine):
                start = datetime.combine(day, datetime.min.time())
                window = ps._all_completed_history(session, start, "football")
                matches = by_day[day]
                shared = ps._shared_fits_for(
                    window, sorted({m.competition for m in matches}, key=str)
                )
                for m in matches:
                    try:
                        out = predict_match(
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
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("match %s skipped: %s", m.id, exc)
                        continue
                    payload = {
                        "home_win": out.home_win,
                        "draw": out.draw,
                        "away_win": out.away_win,
                        "btts_yes": out.prob_btts_yes,
                        "btts_no": out.prob_btts_no,
                        "goals_markets": out.goals_markets,
                        "ht_goals_markets": out.ht_goals_markets,
                        "corners_markets": out.corners_markets,
                        "cards_markets": out.cards_markets,
                    }
                    # The read-time corner curves apply to both variants, as they do live.
                    calibrate_payload(payload)
                    if variant == "old":
                        h, d, a = apply_result_calibration(
                            payload["home_win"] / 100,
                            payload["draw"] / 100,
                            payload["away_win"] / 100,
                            *OLD_RESULT_CORRECTION,
                        )
                        payload["home_win"] = round(h * 100, 1)
                        payload["draw"] = round(d * 100, 1)
                        payload["away_win"] = round(a * 100, 1)
                    elif _registered_result_correction_active(session):
                        raise SystemExit(
                            "A match-result correction is registered; clear it first "
                            "(python -m ml.training.calibrate_match_result --clear)."
                        )
                    ranked = rank_calls(
                        candidate_calls(payload), competition_base_rates(session, m.competition)
                    )
                    best = headline_call(ranked)
                    result = result_from_match(m)
                    if best is None or result is None:
                        continue
                    outcome = settle_key(best.call.key, result)
                    writer.writerow(
                        [
                            variant,
                            m.id,
                            m.match_date.isoformat(),
                            m.competition,
                            best.call.key,
                            best.call.market,
                            f"{best.call.probability:.1f}",
                            outcome.value,
                            int(best.call.probability >= 70.0),
                        ]
                    )
                if index % 5 == 0:
                    handle.flush()
                    logger.info("%s shard %d: day %d/%d", variant, shard, index + 1, len(mine))
        logger.info("wrote %s", path)
    finally:
        session.close()


_ACTIVE_CACHE: dict = {}


def _registered_result_correction_active(session) -> bool:
    if "v" not in _ACTIVE_CACHE:
        from app.models import ModelVersion

        _ACTIVE_CACHE["v"] = (
            session.query(ModelVersion)
            .filter(
                ModelVersion.model_name == "calibration_match_result",
                ModelVersion.is_active.is_(True),
            )
            .first()
            is not None
        )
    return _ACTIVE_CACHE["v"]


def report() -> None:
    import pandas as pd

    files = sorted(glob.glob(str(OUT_DIR / "best_tips_*_of_*.csv")))
    data = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    data = data[data["outcome"] != "void"]
    both = None
    for variant, g in data.groupby("variant"):
        won = (g["outcome"] == "won").sum()
        strong = g[g["strong"] == 1]
        sw = (strong["outcome"] == "won").sum()
        print(
            f"{variant:<4} n={len(g):>5}  best tips won {100 * won / len(g):5.1f}%   "
            f"strong(70+) n={len(strong):>5} won {100 * sw / len(strong):5.1f}%"
        )
        mix = g["market"].value_counts(normalize=True).head(5)
        print("      mix:", ", ".join(f"{k} {100 * v:.0f}%" for k, v in mix.items()))
        by = g.groupby("market").apply(
            lambda x: f"{(x['outcome'] == 'won').mean() * 100:.0f}% of {len(x)}",
            include_groups=False,
        )
        print("      win by market:", ", ".join(f"{k} {v}" for k, v in by.items()))
        both = g if both is None else both
    old = data[data["variant"] == "old"].set_index("match_id")
    new = data[data["variant"] == "new"].set_index("match_id")
    common = old.index.intersection(new.index)
    if len(common):
        o, n = old.loc[common], new.loc[common]
        print(
            f"\nsame {len(common)} matches: old {100 * (o['outcome'] == 'won').mean():.1f}%  "
            f"new {100 * (n['outcome'] == 'won').mean():.1f}%   "
            f"same tip chosen on {100 * (o['key'] == n['key']).mean():.0f}%"
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--variant", choices=["old", "new"], required=True)
    r.add_argument("--shard", type=int, default=0)
    r.add_argument("--of", type=int, default=1)
    r.add_argument("--every", type=int, default=3)
    sub.add_parser("report")
    args = parser.parse_args()
    if args.command == "run":
        run(args.variant, args.shard, args.of, args.every)
    else:
        report()


if __name__ == "__main__":
    main()
