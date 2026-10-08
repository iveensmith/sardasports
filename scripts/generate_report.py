"""Generate the performance dashboard: backfill results, calibration chart, drift check.

Step 11 of the spec. Real numbers only — everything here reads from
`prediction_history`/`training_runs`, computed by `ml.monitoring.*`; nothing
is invented if there isn't enough data yet (it says so explicitly instead).

Usage:
    uv run python scripts/generate_report.py
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless — this runs as a script/cron job, not in a GUI
import matplotlib.pyplot as plt

from app.database.session import SessionLocal
from ml.monitoring.calibration import build_calibration_report
from ml.monitoring.drift import check_drift
from ml.monitoring.evaluation import backfill_actual_results

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "reports"


def render_calibration_chart(report, out_path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    if report.buckets:
        predicted = [b.mean_predicted_probability for b in report.buckets]
        actual = [b.actual_accuracy for b in report.buckets]
        sizes = [max(20, b.count * 3) for b in report.buckets]

        ax1.plot([0, 100], [0, 100], "--", color="gray", label="Perfect calibration")
        ax1.scatter(predicted, actual, s=sizes, color="#2563eb", alpha=0.8, label="Observed")
        ax1.set_xlabel("Predicted probability (%)")
        ax1.set_ylabel("Actual accuracy (%)")
        ax1.set_title("Calibration curve")
        ax1.set_xlim(0, 100)
        ax1.set_ylim(0, 100)
        ax1.legend()

        counts = [b.count for b in report.buckets]
        labels = [f"{int(b.bucket_low)}-{int(b.bucket_high)}" for b in report.buckets]
        ax2.bar(labels, counts, color="#2563eb")
        ax2.set_xlabel("Predicted probability bucket (%)")
        ax2.set_ylabel("Number of predictions")
        ax2.set_title("Prediction volume by confidence bucket")
        plt.setp(ax2.get_xticklabels(), rotation=45, ha="right")
    else:
        for ax in (ax1, ax2):
            ax.text(0.5, 0.5, "Not enough evaluated predictions yet", ha="center", va="center")
            ax.set_axis_off()

    fig.suptitle(
        f"SARDASPORTS calibration report — {report.num_predictions} evaluated predictions, "
        f"Brier score {report.brier_score}"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def main() -> None:
    session = SessionLocal()
    try:
        updated = backfill_actual_results(session)
        logger.info("Backfilled %d newly-completed predictions", updated)

        report = build_calibration_report(session)
        logger.info(
            "Calibration: %d predictions, accuracy=%.1f%%, Brier=%.4f",
            report.num_predictions,
            report.overall_accuracy,
            report.brier_score,
        )

        drift = check_drift(session)
        for reason in drift.reasons:
            logger.info("Drift check: %s", reason)

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        out_path = REPORTS_DIR / f"calibration_{timestamp}.png"
        render_calibration_chart(report, out_path)
        logger.info("Saved chart to %s", out_path)
    finally:
        session.close()


if __name__ == "__main__":
    main()
