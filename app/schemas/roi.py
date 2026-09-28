"""ROI backtest response schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BacktestBetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    match_id: int
    outcome: str
    edge: float
    odds: float
    stake: float
    won: bool
    profit: float


class BacktestResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    bets: list[BacktestBetOut]
    disclaimer: str = (
        "A retrospective simulation over the model's held-out test matches only. "
        "Not a profit guarantee and not evidence of future performance."
    )
