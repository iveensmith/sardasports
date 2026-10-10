"""Replay the match-result estimators over the matches the active models never saw.

The engine's home / draw / away number is a blend of three estimators (Elo, a Poisson
goals model, and an XGBoost model). To judge any change to that blend honestly it has to be
scored on matches none of its parts were fitted on, so this replays `predict_match` over every
completed football match from `HOLD_OUT_FROM` (the start of the active models' hold-out),
one day at a time with the history cut at the start of each day, and writes each estimator's
own probabilities, the blended ones and the real result.

Sharded like `calibrate_count_markets`: several processes can each take a share of the days.

Usage:
    python -m ml.training.replay_match_result --shard 0 --of 6
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime

import pandas as pd

from app.database.session import SessionLocal
from app.models import Match
from ml.training.calibrate_count_markets import HOLD_OUT_FROM, OUT_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def result_replay_path(shard: int, of: int):
    return OUT_DIR / f"result_replay_{shard}_of_{of}.csv"


def replay(shard: int, of: int) -> None:
    from app.services import prediction_service as ps
    from app.services.elo_service import get_team_elo_before
    from app.utils.config import get_settings
    from ml.prediction.predict import predict_match

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
                Match.away_score.is_not(None),
            )
            .order_by(Match.match_date.asc())
            .all()
        )
        by_day: dict = {}
        for m in rows:
            by_day.setdefault(m.match_date.date(), []).append(m)
        days = sorted(by_day)
        mine = [d for i, d in enumerate(days) if i % of == shard]
        logger.info("shard %d/%d: %d of %d days", shard, of, len(mine), len(days))

        xgb_model, xgb_scaler, _ = ps._get_active_model(
            session, ps.MATCH_RESULT_MODEL_NAME, ps._load_xgboost_cached
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
                        shared=shared.get(m.competition),
                    )
                except Exception as exc:  # noqa: BLE001 - one bad fixture must not stop a replay
                    logger.warning("match %s skipped: %s", m.id, exc)
                    continue
                est = result.estimator_probs
                if "xgboost" not in est:
                    continue
                margin = m.home_score - m.away_score
                outcome = 0 if margin > 0 else 1 if margin == 0 else 2
                out.append(
                    {
                        "match_id": m.id,
                        "competition": m.competition,
                        "date": m.match_date.isoformat(),
                        "outcome": outcome,
                        **{f"{k}_{s}": est[k][i] / 100.0 for k in est for i, s in enumerate("hda")},
                        "blend_h": result.home_win / 100.0,
                        "blend_d": result.draw / 100.0,
                        "blend_a": result.away_win / 100.0,
                    }
                )
            if index % 20 == 0:
                logger.info("shard %d: day %d/%d, %d rows", shard, index + 1, len(mine), len(out))
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(out).to_csv(result_replay_path(shard, of), index=False)
        logger.info("shard %d wrote %d rows", shard, len(out))
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", type=int, required=True)
    parser.add_argument("--of", type=int, default=6)
    args = parser.parse_args()
    replay(args.shard, args.of)


if __name__ == "__main__":
    main()
