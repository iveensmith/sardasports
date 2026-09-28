"""Model drift monitoring.

Compares successive training runs' recorded metrics (real numbers from
`training_runs`, never estimated) and flags when accuracy drops or log-loss
rises beyond a threshold — the trigger a real retraining pipeline would use
to alert a human rather than silently deploying a worse model.

Also compares *feature* distributions between runs (`check_feature_drift`),
independent of the label — e.g. `elo_diff`'s mean shifting a lot between two
training runs can signal that the league's competitive balance changed, new
teams entered, or an ingestion bug altered the data, even before it shows up
as an accuracy drop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import TrainingRun

ACCURACY_DROP_THRESHOLD = 0.05  # 5 percentage points
LOG_LOSS_INCREASE_THRESHOLD = 0.10
FEATURE_SHIFT_THRESHOLD = 0.5  # in units of the earlier run's std deviation


@dataclass
class DriftStatus:
    model_name: str
    has_enough_history: bool
    latest_accuracy: float | None
    previous_accuracy: float | None
    accuracy_delta: float | None
    latest_log_loss: float | None
    previous_log_loss: float | None
    log_loss_delta: float | None
    drift_detected: bool
    reasons: list[str]


def check_drift(session: Session, model_name: str = "xgboost_match_result") -> DriftStatus:
    """Compare the two most recent successful training runs for `model_name`."""
    runs = (
        session.query(TrainingRun)
        .filter(TrainingRun.model_name == model_name, TrainingRun.status == "success")
        .order_by(TrainingRun.started_at.desc())
        .limit(2)
        .all()
    )

    if len(runs) < 2:
        return DriftStatus(
            model_name=model_name,
            has_enough_history=False,
            latest_accuracy=runs[0].metrics.get("accuracy") if runs else None,
            previous_accuracy=None,
            accuracy_delta=None,
            latest_log_loss=runs[0].metrics.get("log_loss") if runs else None,
            previous_log_loss=None,
            log_loss_delta=None,
            drift_detected=False,
            reasons=["Fewer than 2 successful training runs — nothing to compare yet."],
        )

    latest, previous = runs[0], runs[1]
    latest_acc = latest.metrics.get("accuracy")
    previous_acc = previous.metrics.get("accuracy")
    latest_ll = latest.metrics.get("log_loss")
    previous_ll = previous.metrics.get("log_loss")

    reasons = []
    accuracy_delta = (
        (latest_acc - previous_acc)
        if (latest_acc is not None and previous_acc is not None)
        else None
    )
    log_loss_delta = (
        (latest_ll - previous_ll) if (latest_ll is not None and previous_ll is not None) else None
    )

    if accuracy_delta is not None and accuracy_delta < -ACCURACY_DROP_THRESHOLD:
        reasons.append(
            f"Accuracy dropped {abs(accuracy_delta) * 100:.1f} points vs. the previous run."
        )
    if log_loss_delta is not None and log_loss_delta > LOG_LOSS_INCREASE_THRESHOLD:
        reasons.append(f"Log-loss increased by {log_loss_delta:.3f} vs. the previous run.")

    return DriftStatus(
        model_name=model_name,
        has_enough_history=True,
        latest_accuracy=latest_acc,
        previous_accuracy=previous_acc,
        accuracy_delta=round(accuracy_delta, 4) if accuracy_delta is not None else None,
        latest_log_loss=latest_ll,
        previous_log_loss=previous_ll,
        log_loss_delta=round(log_loss_delta, 4) if log_loss_delta is not None else None,
        drift_detected=bool(reasons),
        reasons=reasons or ["No significant drift detected."],
    )


@dataclass
class FeatureShift:
    feature: str
    previous_mean: float
    latest_mean: float
    previous_std: float
    shift: float  # |latest_mean - previous_mean| / previous_std, 0 if previous_std is 0


@dataclass
class FeatureDriftStatus:
    model_name: str
    has_enough_history: bool
    shifted_features: list[FeatureShift] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def drift_detected(self) -> bool:
        return bool(self.shifted_features)


def check_feature_drift(
    session: Session, model_name: str = "xgboost_match_result"
) -> FeatureDriftStatus:
    """Compare each feature's mean between the two most recent successful training
    runs' `feature_summary` (see `ml.training.common.compute_feature_summary`),
    flagging any that moved more than `FEATURE_SHIFT_THRESHOLD` standard
    deviations (measured against the *earlier* run's spread).
    """
    runs = (
        session.query(TrainingRun)
        .filter(TrainingRun.model_name == model_name, TrainingRun.status == "success")
        .order_by(TrainingRun.started_at.desc())
        .limit(2)
        .all()
    )

    if len(runs) < 2:
        return FeatureDriftStatus(
            model_name=model_name,
            has_enough_history=False,
            reasons=["Fewer than 2 successful training runs — nothing to compare yet."],
        )

    latest_summary = runs[0].metrics.get("feature_summary") or {}
    previous_summary = runs[1].metrics.get("feature_summary") or {}
    if not latest_summary or not previous_summary:
        return FeatureDriftStatus(
            model_name=model_name,
            has_enough_history=False,
            reasons=["One or both training runs predate feature_summary tracking."],
        )

    shifted = []
    for feature, previous_stats in previous_summary.items():
        latest_stats = latest_summary.get(feature)
        if latest_stats is None:
            continue

        previous_mean, previous_std = previous_stats["mean"], previous_stats["std"]
        latest_mean = latest_stats["mean"]
        shift = abs(latest_mean - previous_mean) / previous_std if previous_std > 0 else 0.0

        if shift > FEATURE_SHIFT_THRESHOLD:
            shifted.append(
                FeatureShift(
                    feature=feature,
                    previous_mean=previous_mean,
                    latest_mean=latest_mean,
                    previous_std=previous_std,
                    shift=round(shift, 2),
                )
            )

    shifted.sort(key=lambda s: s.shift, reverse=True)
    reasons = [
        f"{s.feature} shifted {s.shift:.1f} std devs (mean {s.previous_mean} -> {s.latest_mean})"
        for s in shifted
    ] or ["No significant feature drift detected."]
    return FeatureDriftStatus(
        model_name=model_name, has_enough_history=True, shifted_features=shifted, reasons=reasons
    )
