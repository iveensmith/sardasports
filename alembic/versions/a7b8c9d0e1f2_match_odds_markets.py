"""best market prices per fixture

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-29

`matches.odds_markets` holds the best available price per selection across
bookmakers, for the markets the engine can price (match winner, goals lines,
both teams to score). The existing odds_home_win/draw/away columns are left
alone: value detection and the ROI backtest read them, and historical rows
only ever carried 1X2.

JSON rather than more float columns because the line set is not fixed — it
changed once already when goals went multi-line — and a row is only read
whole, never queried by selection.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("odds_markets", sa.JSON(), nullable=True))
    op.add_column("matches", sa.Column("odds_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "odds_updated_at")
    op.drop_column("matches", "odds_markets")
