"""add half-time goals to matches

Revision ID: b999d3af622b
Revises: 54ea77c61da2
Create Date: 2026-09-23 16:36:25.152563

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b999d3af622b"
down_revision: str | None = "54ea77c61da2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also proposed ALTER COLUMN ... NOT NULL on
    # predictions/prediction_history.corners_markets/cards_markets (the ORM
    # model's `Mapped[list]` type hint implies NOT NULL, but the actual
    # column is deliberately nullable=True — see the migration that added
    # it, 54ea77c61da2, for why). Left out here: those columns already have
    # real NULL rows from before they existed, and that ALTER would fail
    # against them. This migration stays scoped to the Match table.
    op.add_column("matches", sa.Column("home_ht_goals", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("away_ht_goals", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "away_ht_goals")
    op.drop_column("matches", "home_ht_goals")
