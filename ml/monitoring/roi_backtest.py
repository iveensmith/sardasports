"""ROI backtest: what would flat-staking every detected value edge have returned?

Critically, this only ever runs over matches the active models never trained
on. `ml.training.common.time_based_split` holds out the most recent
`test_fraction` of matches (chronologically) from every training run;
`resolve_test_period_start` re-derives that same cutoff date from the same
processed dataset, so the backtest is restricted to the same genuinely
out-of-sample matches the model's own reported accuracy/log-loss come from.
Backtesting over matches the model trained on would be look-ahead bias and
would make the ROI number meaningless.

Still, per `rag/knowledge_base/value_betting_concepts.md`: this is a
retrospective simulation over one league's ~1-2 seasons of history, not a
profit guarantee or a claim it will hold going forward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Match
from app.services.prediction_service import predict_for_match
from app.utils.config import get_settings
from ml.monitoring.evaluation import actual_result_label
from ml.monitoring.value_detection import compute_value_edges
from ml.training.common import build_feature_frame, load_processed_matches, time_based_split


def resolve_test_period_start(test_fraction: float = 0.2) -> datetime | None:
    """The match_date of the first row in the held-out test split, or None if
    `data/processed/matches.csv` doesn't exist / has too little data.

    Delegates the "does the file exist / is there enough data" check to
    `load_processed_matches` itself (single source of truth for
    `PROCESSED_PATH`) rather than duplicating a separate existence check here.
    """
    try:
        matches = load_processed_matches(min_matches=1)
    except SystemExit:
        return None

    settings = get_settings()
    frame = build_feature_frame(matches, settings)
    _, test_df = time_based_split(frame, test_fraction)
    if test_df.empty:
        return None
    return test_df["match_date"].min().to_pydatetime()


@dataclass
class BacktestBet:
    match_id: int
    outcome: str
    edge: float
    odds: float
    stake: float
    won: bool
    profit: float


@dataclass
class BacktestResult:
    edge_threshold: float
    stake_per_bet: float
    num_matches_considered: int
    num_bets: int
    num_wins: int
    total_staked: float
    total_returned: float
    profit: float
    roi_percent: float
    hit_rate_percent: float
    bets: list[BacktestBet] = field(default_factory=list)


def run_backtest(
    session: Session, edge_threshold: float = 5.0, stake: float = 1.0, test_fraction: float = 0.2
) -> BacktestResult:
    """Simulate flat-staking `stake` on every outcome where the model's edge over the
    market exceeded `edge_threshold` percentage points, across the held-out test period.
    """
    cutoff = resolve_test_period_start(test_fraction)
    if cutoff is None:
        return BacktestResult(
            edge_threshold=edge_threshold,
            stake_per_bet=stake,
            num_matches_considered=0,
            num_bets=0,
            num_wins=0,
            total_staked=0.0,
            total_returned=0.0,
            profit=0.0,
            roi_percent=0.0,
            hit_rate_percent=0.0,
        )

    candidates = (
        session.query(Match)
        .filter(
            Match.status == "completed",
            Match.match_date >= cutoff,
            Match.odds_home_win.isnot(None),
            Match.odds_draw.isnot(None),
            Match.odds_away_win.isnot(None),
        )
        .order_by(Match.match_date.asc())
        .all()
    )

    bets: list[BacktestBet] = []
    for match in candidates:
        prediction = predict_for_match(session, match.id)
        edges = compute_value_edges(
            model_home=prediction["home_win"],
            model_draw=prediction["draw"],
            model_away=prediction["away_win"],
            odds_home=match.odds_home_win,
            odds_draw=match.odds_draw,
            odds_away=match.odds_away_win,
        )
        actual = actual_result_label(match.home_score, match.away_score)
        odds_by_outcome = {
            "home_win": match.odds_home_win,
            "draw": match.odds_draw,
            "away_win": match.odds_away_win,
        }

        for e in edges:
            if e.edge < edge_threshold:
                continue  # edges are sorted descending, but check every outcome independently
            won = e.outcome == actual
            odds = odds_by_outcome[e.outcome]
            payout = odds * stake if won else 0.0
            bets.append(
                BacktestBet(
                    match_id=match.id,
                    outcome=e.outcome,
                    edge=round(e.edge, 1),
                    odds=odds,
                    stake=stake,
                    won=won,
                    profit=round(payout - stake, 2),
                )
            )

    total_staked = sum(b.stake for b in bets)
    total_returned = sum(b.stake + b.profit for b in bets)
    profit = total_returned - total_staked
    num_wins = sum(1 for b in bets if b.won)

    return BacktestResult(
        edge_threshold=edge_threshold,
        stake_per_bet=stake,
        num_matches_considered=len(candidates),
        num_bets=len(bets),
        num_wins=num_wins,
        total_staked=round(total_staked, 2),
        total_returned=round(total_returned, 2),
        profit=round(profit, 2),
        roi_percent=round(100 * profit / total_staked, 2) if total_staked else 0.0,
        hit_rate_percent=round(100 * num_wins / len(bets), 1) if bets else 0.0,
        bets=bets,
    )
