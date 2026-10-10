"""Pull the corner and match-result probabilities back to what the record says they deserve.

Graded out of sample (the engine replayed over the fifteen months its models had never seen),
the corner lines ran about five points too confident on average, while the card lines were
already well calibrated. A logistic curve per line, fitted by
`ml.training.calibrate_count_markets` and kept in the model registry as
`calibration_<market>_over_<line>`, fixes the corners. Only lines whose curve beat the raw
probabilities on held-back matches by more than noise are registered, so a line without a
curve is simply left as the engine computed it.

The curves are applied where a prediction is *read*, never where it is stored: a stored row
keeps the number the engine first produced, and every reader (the board, the match page, the
track record, the market pages) sees the same calibrated figure whether the prediction was
computed a moment ago or stored months back. Applying it in both places would correct twice.

The home / draw / away figures get the same treatment from one registered correction,
`calibration_match_result` (`ml.training.calibrate_match_result`): replayed out of sample, the
blend claimed home wins 2 points too often and draws 2 points too rarely in every period.
Double chance and the match-result calls are derived from those three figures, so they follow.
"""

from __future__ import annotations

import logging

from app.database.session import SessionLocal
from app.models import ModelVersion
from app.utils.coalesce import CoalescingCache

logger = logging.getLogger(__name__)

_CURVES = CoalescingCache(600, max_entries=1, max_concurrent=1, copy_results=False)
MARKET_FIELDS = (("corners", "corners_markets"), ("cards", "cards_markets"))


def _load() -> dict:
    """{"curves": {(market, line): (slope, intercept)}, "result": (scale, home, draw) | None}."""
    session = SessionLocal()
    try:
        versions = (
            session.query(ModelVersion)
            .filter(
                ModelVersion.is_active.is_(True),
                ModelVersion.model_name.like("calibration_%"),
            )
            .all()
        )
        curves = {}
        result = None
        for version in versions:
            metrics = version.metrics or {}
            if {"market", "line", "slope", "intercept"} <= metrics.keys():
                curves[(metrics["market"], float(metrics["line"]))] = (
                    float(metrics["slope"]),
                    float(metrics["intercept"]),
                )
            elif (
                metrics.get("market") == "match_result"
                and {
                    "scale",
                    "home_offset",
                    "draw_offset",
                }
                <= metrics.keys()
            ):
                result = (
                    float(metrics["scale"]),
                    float(metrics["home_offset"]),
                    float(metrics["draw_offset"]),
                )
        return {"curves": curves, "result": result}
    except Exception:  # noqa: BLE001 - uncalibrated beats no prediction
        logger.exception("could not load the calibration curves")
        session.rollback()
        return {"curves": {}, "result": None}
    finally:
        session.close()


def clear_cache() -> None:
    _CURVES.clear()


def _calibrate_result(payload: dict, params: tuple[float, float, float]) -> None:
    from ml.training.calibrate_match_result import apply_result_calibration

    figures = [payload.get(k) for k in ("home_win", "draw", "away_win")]
    if any(v is None for v in figures):
        return
    calibrated = apply_result_calibration(*(v / 100.0 for v in figures), *params)
    rounded = [round(v * 100, 1) for v in calibrated]
    # Rounding each to a tenth can leave the three a tenth off 100; give that to the likeliest.
    rounded[rounded.index(max(rounded))] = round(100.0 - sum(rounded) + max(rounded), 1)
    payload["home_win"], payload["draw"], payload["away_win"] = rounded


def calibrate_payload(payload: dict) -> dict:
    """Replace `payload`'s corner lines and result figures with calibrated copies.

    Returns `payload`.
    """
    from ml.training.calibrate_count_markets import apply_curve

    loaded = _CURVES.get_or_compute("curves", _load)
    curves = loaded["curves"]
    if loaded["result"] is not None:
        _calibrate_result(payload, loaded["result"])
    if not curves:
        return payload
    for market, field in MARKET_FIELDS:
        entries = payload.get(field)
        if not entries:
            continue
        adjusted = []
        for entry in entries:
            curve = curves.get((market, float(entry["line"])))
            if curve is None or entry.get("prob_over") is None:
                adjusted.append(entry)
                continue
            calibrated = apply_curve(entry["prob_over"] / 100.0, *curve)
            adjusted.append(
                {
                    **entry,
                    "prob_over": round(calibrated * 100, 1),
                    "prob_under": round((1 - calibrated) * 100, 1),
                }
            )
        payload[field] = adjusted
    return payload
