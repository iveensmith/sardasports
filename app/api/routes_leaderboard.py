"""GET /model/leaderboard — every trained model on one scoreboard.

Additive: it reads the same `model_versions` rows `/model/performance`
serves, in one request rather than one per model. The analytics page was
making nineteen round trips to assemble this.

**Ranked by edge, not accuracy.** Accuracy on its own is close to
meaningless across markets: a line that falls one way 78% of the time gives
a model 78% for learning nothing. Every trainer records the baseline its
market actually has to beat — the majority class for a binary line, "always
pick the home side" for a basketball winner, "always pick the higher-rated
player" for tennis — and the edge over that baseline is what this ranks on.

**Small samples are flagged, not hidden.** A model evaluated on a few
hundred matches can top a table on noise alone, so anything below
`PROVISIONAL_SAMPLE_THRESHOLD` carries a flag and sorts after models with
a real sample at comparable edge.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import ModelVersion

router = APIRouter(tags=["models"])

# Below this many held-out matches, an edge is not distinguishable from
# noise at the margins these models operate on (a percentage point or two).
# Chosen as a round figure in the same spirit as the sample cutoffs betting
# track records use, and reported rather than applied silently.
PROVISIONAL_SAMPLE_THRESHOLD = 1000

# The baselines trainers record, in the order they should be preferred, with
# the human phrasing for each. A model may record more than one.
BASELINE_KEYS: list[tuple[str, str]] = [
    ("elo_baseline_accuracy", "Always pick the higher rating"),
    ("home_win_base_rate", "Always pick the home side"),
    ("majority_class_base_rate", "Always pick the majority class"),
]

# Presentation metadata for the registry's machine names. Kept here rather
# than parsed out of the name, which encodes a line ("..._corners_8_5") in a
# form that is convenient for the registry and unreadable in a table.
CATALOG: dict[str, tuple[str, str, str]] = {
    "xgboost_match_result": ("Match result", "football", "1X2"),
    "gbm_btts": ("Both teams to score", "football", "BTTS"),
    "lightgbm_over_under_1_5": ("Goals over 1.5", "football", "Goals"),
    "lightgbm_over_under_2_5": ("Goals over 2.5", "football", "Goals"),
    "lightgbm_over_under_ht_goals_0_5": ("Half-time goals over 0.5", "football", "Goals"),
    "lightgbm_over_under_corners_7_5": ("Corners over 7.5", "football", "Corners"),
    "lightgbm_over_under_corners_8_5": ("Corners over 8.5", "football", "Corners"),
    "lightgbm_over_under_corners_9_5": ("Corners over 9.5", "football", "Corners"),
    "gbm_over_under_cards_2_5": ("Cards over 2.5", "football", "Cards"),
    "gbm_over_under_cards_3_5": ("Cards over 3.5", "football", "Cards"),
    "gbm_over_under_cards_4_5": ("Cards over 4.5", "football", "Cards"),
    "lightgbm_basketball_winner": ("NBA winner", "basketball", "Moneyline"),
    "lightgbm_basketball_total_215_5": ("NBA total 215.5", "basketball", "Totals"),
    "lightgbm_basketball_total_225_5": ("NBA total 225.5", "basketball", "Totals"),
    "lightgbm_basketball_total_235_5": ("NBA total 235.5", "basketball", "Totals"),
    "lightgbm_tennis_winner": ("Tennis winner", "tennis", "Moneyline"),
    "lightgbm_tennis_total_games_19_5": ("Tennis games over 19.5", "tennis", "Totals"),
    "lightgbm_tennis_total_games_21_5": ("Tennis games over 21.5", "tennis", "Totals"),
    "lightgbm_tennis_total_games_23_5": ("Tennis games over 23.5", "tennis", "Totals"),
}

SORTABLE = {"edge", "accuracy", "log_loss", "samples"}


def _baseline(metrics: dict) -> tuple[float | None, str | None]:
    for key, label in BASELINE_KEYS:
        value = metrics.get(key)
        if isinstance(value, int | float):
            return float(value) * 100, label
    return None, None


def _row(active: ModelVersion, previous: ModelVersion | None) -> dict | None:
    metrics = active.metrics or {}
    accuracy = metrics.get("accuracy")
    if not isinstance(accuracy, int | float):
        return None

    label, sport, market = CATALOG.get(active.model_name, (active.model_name, "unknown", "—"))
    baseline, baseline_kind = _baseline(metrics)
    samples = metrics.get("num_test_samples")

    # Change since the previous trained version of this same model. Absent
    # rather than zero when there is no earlier version to compare against —
    # a first-ever model has no trend, which is different from a flat one.
    trend = None
    if previous is not None:
        earlier = (previous.metrics or {}).get("accuracy")
        if isinstance(earlier, int | float):
            trend = round((accuracy - earlier) * 100, 2)

    return {
        "model_name": active.model_name,
        "label": label,
        "sport": sport,
        "market": market,
        "version": active.version,
        "trained_at": active.trained_at.isoformat() if active.trained_at else None,
        "accuracy": round(accuracy * 100, 2),
        "log_loss": (
            round(float(metrics["log_loss"]), 4)
            if isinstance(metrics.get("log_loss"), int | float)
            else None
        ),
        "baseline": None if baseline is None else round(baseline, 2),
        "baseline_kind": baseline_kind,
        "edge": None if baseline is None else round(accuracy * 100 - baseline, 2),
        "samples": samples if isinstance(samples, int) else None,
        "provisional": (isinstance(samples, int) and samples < PROVISIONAL_SAMPLE_THRESHOLD),
        "trend": trend,
    }


@router.get("/model/leaderboard")
def model_leaderboard(
    sport: str | None = Query(default=None),
    sort: str = Query(default="edge", pattern="^(edge|accuracy|log_loss|samples)$"),
    db: Session = Depends(get_db),
) -> dict:
    """Every active model, ranked.

    Models with no recorded baseline are returned with `edge: null` and sort
    last rather than being dropped or credited with a flattering zero — a
    missing benchmark is a gap in what we know, not a neutral result.
    """
    active_versions = (
        db.query(ModelVersion)
        .filter(ModelVersion.is_active.is_(True))
        .order_by(ModelVersion.model_name.asc())
        .all()
    )

    rows = []
    for active in active_versions:
        previous = (
            db.query(ModelVersion)
            .filter(
                ModelVersion.model_name == active.model_name,
                ModelVersion.id != active.id,
            )
            .order_by(ModelVersion.trained_at.desc())
            .first()
        )
        row = _row(active, previous)
        if row is not None and (sport is None or row["sport"] == sport):
            rows.append(row)

    def sort_key(row: dict):
        # A provisional sample sorts behind a real one at equal standing, so
        # a small-sample fluke never takes the top of the board outright.
        value = row.get(sort)
        missing = value is None
        # log_loss is better when lower; the rest are better when higher.
        ordered = value if sort == "log_loss" else -(value or 0)
        return (missing, row["provisional"], ordered)

    rows.sort(key=sort_key)
    for position, row in enumerate(rows, start=1):
        row["rank"] = position

    with_baseline = [r for r in rows if r["edge"] is not None]
    return {
        "sort": sort,
        "count": len(rows),
        "provisional_threshold": PROVISIONAL_SAMPLE_THRESHOLD,
        "summary": {
            "with_baseline": len(with_baseline),
            "beating_baseline": sum(1 for r in with_baseline if r["edge"] > 1),
            "provisional": sum(1 for r in rows if r["provisional"]),
        },
        "models": rows,
    }
