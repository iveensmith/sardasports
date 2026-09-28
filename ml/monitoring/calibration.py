"""Calibration tracking — is a 70% prediction right ~70% of the time?

Operates on evaluated `prediction_history` rows (those with actual results
backfilled by `ml.monitoring.evaluation.backfill_actual_results`). All
metrics here are computed from real recorded predictions vs. real outcomes —
nothing is simulated.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import PredictionHistory
from ml.monitoring.evaluation import actual_result_label, predicted_result_label


@dataclass
class EvaluatedPrediction:
    prob_home: float
    prob_draw: float
    prob_away: float
    confidence: float
    predicted_label: str
    actual_label: str

    @property
    def was_correct(self) -> bool:
        return self.predicted_label == self.actual_label


@dataclass
class CalibrationBucket:
    bucket_low: float
    bucket_high: float
    count: int
    mean_predicted_probability: float
    actual_accuracy: float


@dataclass
class CalibrationReport:
    num_predictions: int
    brier_score: float  # 0 (perfect) to 2 (worst), multi-class Brier
    overall_accuracy: float
    buckets: list[CalibrationBucket]


def get_evaluated_predictions(session: Session) -> list[EvaluatedPrediction]:
    """All prediction_history rows whose match has completed."""
    rows = (
        session.query(PredictionHistory)
        .filter(PredictionHistory.actual_home_goals.isnot(None))
        .all()
    )
    result = []
    for row in rows:
        actual = actual_result_label(row.actual_home_goals, row.actual_away_goals)
        predicted = predicted_result_label(row.prob_home, row.prob_draw, row.prob_away)
        result.append(
            EvaluatedPrediction(
                # PredictionHistory stores probabilities as 0-1 fractions;
                # everything downstream here (buckets, Brier score) works in
                # 0-100 percentage points, matching `confidence`.
                prob_home=row.prob_home * 100,
                prob_draw=row.prob_draw * 100,
                prob_away=row.prob_away * 100,
                confidence=row.confidence,
                predicted_label=predicted,
                actual_label=actual,
            )
        )
    return result


def brier_score(predictions: list[EvaluatedPrediction]) -> float:
    """Multi-class Brier score: mean squared error between the probability
    vector [P(home), P(draw), P(away)] and the one-hot actual outcome."""
    if not predictions:
        return 0.0

    total = 0.0
    for p in predictions:
        home_actual = 1.0 if p.actual_label == "home_win" else 0.0
        draw_actual = 1.0 if p.actual_label == "draw" else 0.0
        away_actual = 1.0 if p.actual_label == "away_win" else 0.0
        total += (
            (p.prob_home / 100 - home_actual) ** 2
            + (p.prob_draw / 100 - draw_actual) ** 2
            + (p.prob_away / 100 - away_actual) ** 2
        )
    return round(total / len(predictions), 4)


def calibration_buckets(
    predictions: list[EvaluatedPrediction], n_bins: int = 10
) -> list[CalibrationBucket]:
    """Bucket predictions by the probability assigned to the *predicted* outcome.

    E.g. a prediction of "home win, 73%" that actually was a home win lands in
    the 70-80% bucket as a hit; if it wasn't a home win, as a miss. A
    well-calibrated model's `actual_accuracy` should track `bucket` closely.
    """
    bucket_width = 100.0 / n_bins
    buckets: list[CalibrationBucket] = []

    for i in range(n_bins):
        low, high = i * bucket_width, (i + 1) * bucket_width
        in_bucket = [
            p
            for p in predictions
            if low <= max(p.prob_home, p.prob_draw, p.prob_away) < high
            or (high == 100.0 and max(p.prob_home, p.prob_draw, p.prob_away) == 100.0)
        ]
        if not in_bucket:
            continue

        predicted_probs = [max(p.prob_home, p.prob_draw, p.prob_away) for p in in_bucket]
        hits = sum(1 for p in in_bucket if p.was_correct)
        buckets.append(
            CalibrationBucket(
                bucket_low=low,
                bucket_high=high,
                count=len(in_bucket),
                mean_predicted_probability=round(sum(predicted_probs) / len(predicted_probs), 1),
                actual_accuracy=round(100 * hits / len(in_bucket), 1),
            )
        )
    return buckets


def build_calibration_report(session: Session, n_bins: int = 10) -> CalibrationReport:
    predictions = get_evaluated_predictions(session)
    accuracy = (
        round(100 * sum(1 for p in predictions if p.was_correct) / len(predictions), 1)
        if predictions
        else 0.0
    )
    return CalibrationReport(
        num_predictions=len(predictions),
        brier_score=brier_score(predictions),
        overall_accuracy=accuracy,
        buckets=calibration_buckets(predictions, n_bins=n_bins),
    )
