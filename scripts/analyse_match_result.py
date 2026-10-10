"""Score the match-result estimators and candidate blends on the replayed hold-out matches.

Reads `data/processed/calibration/result_replay_*_of_*.csv` (see
`ml/training/replay_match_result.py`). Everything is judged out of sample: blend weights and
calibration are chosen on the earlier 60% of the matches by date and scored on the later 40%.

    python scripts/analyse_match_result.py
"""

from __future__ import annotations

import glob
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EPS = 1e-6


def load() -> pd.DataFrame:
    files = sorted(glob.glob(str(ROOT / "data/processed/calibration/result_replay_*_of_*.csv")))
    frame = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    return frame.sort_values("date").reset_index(drop=True)


def probs(frame: pd.DataFrame, name: str) -> np.ndarray:
    return frame[[f"{name}_h", f"{name}_d", f"{name}_a"]].to_numpy()


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, EPS, 1)
    return float(-np.mean(np.log(p[np.arange(len(y)), y])))


def accuracy(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean(np.argmax(p, axis=1) == y))


def blend(parts: list[np.ndarray], weights) -> np.ndarray:
    mixed = sum(w * p for w, p in zip(weights, parts, strict=True))
    return mixed / mixed.sum(axis=1, keepdims=True)


def temperature(p: np.ndarray, t: float) -> np.ndarray:
    q = np.power(np.clip(p, EPS, 1), 1.0 / t)
    return q / q.sum(axis=1, keepdims=True)


def report(label: str, p: np.ndarray, y: np.ndarray) -> None:
    # "Side" picks: the headline only ever calls Home or Away, never Draw, so also report how
    # often the likelier of the two sides won among decisive-or-not matches.
    side = np.where(p[:, 0] >= p[:, 2], 0, 2)
    print(
        f"  {label:<34} logloss {log_loss(p, y):.4f}  acc {accuracy(p, y):.4f}  "
        f"side-pick {np.mean(side == y):.4f}"
    )


def main() -> None:
    frame = load()
    y = frame["outcome"].to_numpy()
    cut = int(len(frame) * 0.6)
    print(f"{len(frame)} matches, {frame['date'].iloc[0][:10]} .. {frame['date'].iloc[-1][:10]}")
    names = ["elo", "poisson", "xgboost"]
    parts = [probs(frame, n) for n in names]
    current = probs(frame, "blend")

    print("\nAll matches:")
    for n, p in zip(names, parts, strict=True):
        report(n, p, y)
    report("current blend (.25/.35/.40)", current, y)
    print("  always-home base rate:", round(float(np.mean(y == 0)), 4))

    fit_y, test_y = y[:cut], y[cut:]
    print("\nTuning weights on the first 60%, scoring the last 40%:")
    best = None
    for w in itertools.product(np.arange(0, 1.01, 0.05), repeat=3):
        if abs(sum(w) - 1) > 1e-9:
            continue
        loss = log_loss(blend([p[:cut] for p in parts], w), fit_y)
        if best is None or loss < best[0]:
            best = (loss, w)
    w = best[1]
    print("  best weights (elo, poisson, xgboost):", tuple(round(float(x), 2) for x in w))
    report("current blend, test slice", current[cut:], test_y)
    report("tuned weights, test slice", blend([p[cut:] for p in parts], w), test_y)

    print("\nTemperature on the current blend (fit on first 60%):")
    ts = np.arange(0.8, 1.41, 0.02)
    t = min(ts, key=lambda x: log_loss(temperature(current[:cut], x), fit_y))
    print("  best temperature:", round(float(t), 2))
    report("current blend, test slice", current[cut:], test_y)
    report("temperature scaled, test slice", temperature(current[cut:], t), test_y)

    print("\nReliability of the current blend, last 40% (home / draw / away):")
    for col, label in enumerate(("home", "draw", "away")):
        pc = current[cut:, col]
        edges = np.quantile(pc, np.linspace(0, 1, 6))
        for lo, hi in itertools.pairwise(edges):
            mask = (pc >= lo) & (pc <= hi)
            if mask.sum() < 50:
                continue
            print(
                f"  {label:<5} claimed {pc[mask].mean():.3f}  realised "
                f"{np.mean(test_y[mask] == col):.3f}  n={int(mask.sum())}"
            )

    print("\nBy competition, last 40% (n >= 400): home-win claimed vs realised, draw likewise")
    test = frame.iloc[cut:]
    for comp, g in test.groupby("competition"):
        if len(g) < 400:
            continue
        loss = log_loss(probs(g, "blend"), g["outcome"].to_numpy())
        print(
            f"  {comp:<32} n={len(g):>5}  home {g['blend_h'].mean():.3f}/"
            f"{np.mean(g['outcome'] == 0):.3f}  draw {g['blend_d'].mean():.3f}/"
            f"{np.mean(g['outcome'] == 1):.3f}  ll {loss:.4f}"
        )


if __name__ == "__main__":
    main()
