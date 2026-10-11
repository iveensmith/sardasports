"""Calibrate the home / draw / away probabilities.

Why this exists
---------------
Replayed over the 25,000 matches the models never saw (`ml.training.replay_match_result`), the
blended result probabilities lean the same way in every period from September 2024 to now:
home wins are claimed 46.0% of the time and happen 43.8%, draws are claimed 24.1% and happen
26.2%. The cause is the Poisson part, which gives the home side 49.3% on average, and the Elo
part, which hardly ever leans towards a draw; XGBoost alone is almost exact. A home call
claiming 54% therefore wins about 52%, and a "home or draw" figure reads a point or two high.

The fix is one multinomial correction applied to the blend,

    z = scale * log(p) + [home_offset, draw_offset, 0]      p' = softmax(z)

fitted on the earlier 60% of the replayed matches by date and scored on the later 40%. Retuned
blend weights and a separate correction per league were both tried and did worse on the later
40%, so this is deliberately the one global correction and nothing more.

It only changes how sure the engine says it is, not which side it prefers: the more likely
of home and away stays the more likely in about 96% of matches, and accuracy moves by about a
tenth of a point (noise). What improves is that the percentages mean what they say.

Usage:
    python -m ml.training.replay_match_result --shard 0 --of 6     # (all six shards first)
    python -m ml.training.calibrate_match_result [--no-register]

    # Apply numbers fitted elsewhere (e.g. on the production database, which has not run the
    # replay), or switch the correction off. Whenever the blend itself changes (a new goals
    # model, new weights) the old correction no longer fits it: refit, or clear it.
    python -m ml.training.calibrate_match_result --set 1.064 -0.091 0.092
    python -m ml.training.calibrate_match_result --clear
"""

from __future__ import annotations

import argparse
import glob
import logging
import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ml.training.calibrate_count_markets import MIN_IMPROVEMENT, OUT_DIR
from ml.training.common import new_version_string, register_model_version

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_NAME = "calibration_match_result"
FIT_FRACTION = 0.6
MIN_MATCHES = 2000
EPS = 1e-6


def apply_result_calibration(
    home: float, draw: float, away: float, scale: float, home_offset: float, draw_offset: float
) -> tuple[float, float, float]:
    """The calibrated (home, draw, away) for fractions that sum to about 1."""
    z = [
        scale * math.log(max(home, EPS)) + home_offset,
        scale * math.log(max(draw, EPS)) + draw_offset,
        scale * math.log(max(away, EPS)),
    ]
    top = max(z)
    e = [math.exp(v - top) for v in z]
    total = sum(e)
    return e[0] / total, e[1] / total, e[2] / total


def _recalibrate(p: np.ndarray, params) -> np.ndarray:
    scale, home_offset, draw_offset = params
    z = scale * np.log(np.clip(p, EPS, 1)) + np.array([home_offset, draw_offset, 0.0])
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _log_loss(p: np.ndarray, y: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], EPS, 1))))


def _fit_params(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    result = minimize(
        lambda t: _log_loss(_recalibrate(p, t), y), x0=[1.0, 0.0, 0.0], method="Nelder-Mead"
    )
    return result.x


def fit(register: bool = True) -> None:
    files = sorted(glob.glob(str(OUT_DIR / "result_replay_*_of_*.csv")))
    if not files:
        raise SystemExit("No result replay files found; run `replay_match_result` first.")
    data = pd.concat([pd.read_csv(f) for f in files]).sort_values("date").reset_index(drop=True)
    if len(data) < MIN_MATCHES:
        raise SystemExit(f"Only {len(data)} replayed matches; need {MIN_MATCHES}.")
    p = data[["blend_h", "blend_d", "blend_a"]].to_numpy()
    y = data["outcome"].to_numpy()
    cut = int(len(data) * FIT_FRACTION)
    params = _fit_params(p[:cut], y[:cut])
    before = _log_loss(p[cut:], y[cut:])
    after = _log_loss(_recalibrate(p[cut:], params), y[cut:])
    print(f"{len(data)} matches, fitted on {cut}, tested on {len(data) - cut}")
    print(f"curve: scale {params[0]:.3f}, home {params[1]:+.3f}, draw {params[2]:+.3f}")
    print(f"log-loss on the later 40%: {before:.4f} -> {after:.4f}")
    print("claimed -> realised on the later 40% (home / draw):")
    rec = _recalibrate(p[cut:], params)
    for column, label in ((0, "home"), (1, "draw")):
        print(
            f"  {label}: raw {p[cut:, column].mean():.3f}, calibrated {rec[:, column].mean():.3f},"
            f" actual {np.mean(y[cut:] == column):.3f}"
        )
    if before - after < MIN_IMPROVEMENT:
        print("-> does not help on held-back matches; not registered")
        return
    if register:
        scale, home_offset, draw_offset = (float(v) for v in _fit_params(p, y))
        metrics = {
            "market": "match_result",
            "scale": scale,
            "home_offset": home_offset,
            "draw_offset": draw_offset,
            "num_points": int(len(data)),
            "log_loss_before": before,
            "log_loss_after": after,
        }
        register_model_version(
            MODEL_NAME, new_version_string(), "n/a (calibration)", metrics, int(len(data))
        )
        print(f"-> registered {MODEL_NAME}")


def clear() -> int:
    """Switch the correction off. Returns how many registered rows were deactivated."""
    from app.database.session import SessionLocal
    from app.models import ModelVersion

    session = SessionLocal()
    try:
        count = (
            session.query(ModelVersion)
            .filter(ModelVersion.model_name == MODEL_NAME, ModelVersion.is_active.is_(True))
            .update({"is_active": False})
        )
        session.commit()
    finally:
        session.close()
    clear_cache()
    return count


def set_values(scale: float, home_offset: float, draw_offset: float) -> None:
    """Register a correction fitted elsewhere, replacing the active one."""
    metrics = {
        "market": "match_result",
        "scale": float(scale),
        "home_offset": float(home_offset),
        "draw_offset": float(draw_offset),
        "source": "set by hand",
    }
    register_model_version(MODEL_NAME, new_version_string(), "n/a (calibration)", metrics, 0)
    clear_cache()


def clear_cache() -> None:
    from app.services.count_calibration import clear_cache as _clear

    _clear()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-register", action="store_true")
    parser.add_argument("--clear", action="store_true", help="deactivate the registered correction")
    parser.add_argument(
        "--set",
        nargs=3,
        type=float,
        metavar=("SCALE", "HOME", "DRAW"),
        help="register a correction fitted elsewhere",
    )
    args = parser.parse_args()
    if args.clear:
        print(f"deactivated {clear()} registered correction(s)")
        return
    if args.set:
        set_values(*args.set)
        scale, home, draw = args.set
        print(f"registered {MODEL_NAME}: scale {scale}, home {home}, draw {draw}")
        return
    fit(register=not args.no_register)


if __name__ == "__main__":
    main()
