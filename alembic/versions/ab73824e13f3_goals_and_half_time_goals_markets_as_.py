"""goals and half-time goals markets as multi-line JSON

Revision ID: ab73824e13f3
Revises: b999d3af622b
Create Date: 2026-09-23 16:42:25.619083

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ab73824e13f3"
down_revision: str | None = "b999d3af622b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # nullable=True (not autogenerate's default False) for the same reason
    # as 54ea77c61da2 (corners_markets/cards_markets): existing rows have no
    # value for these new columns. Autogenerate also proposed ALTER COLUMN
    # ... NOT NULL on corners_markets/cards_markets themselves (the ORM
    # model's `Mapped[list]` type hint implies NOT NULL, but they're
    # deliberately nullable — see 54ea77c61da2) — left out here too, for the
    # same reason: real NULL rows already exist there.
    op.add_column("prediction_history", sa.Column("goals_markets", sa.JSON(), nullable=True))
    op.add_column("prediction_history", sa.Column("ht_goals_markets", sa.JSON(), nullable=True))
    op.drop_column("prediction_history", "prob_over_2_5")
    op.drop_column("prediction_history", "prob_under_2_5")
    op.add_column("predictions", sa.Column("goals_markets", sa.JSON(), nullable=True))
    op.add_column("predictions", sa.Column("ht_goals_markets", sa.JSON(), nullable=True))
    op.drop_column("predictions", "prob_over_2_5")
    op.drop_column("predictions", "prob_under_2_5")


def downgrade() -> None:
    op.add_column("predictions", sa.Column("prob_under_2_5", sa.Float(), nullable=True))
    op.add_column("predictions", sa.Column("prob_over_2_5", sa.Float(), nullable=True))
    op.drop_column("predictions", "ht_goals_markets")
    op.drop_column("predictions", "goals_markets")
    op.add_column("prediction_history", sa.Column("prob_under_2_5", sa.Float(), nullable=True))
    op.add_column("prediction_history", sa.Column("prob_over_2_5", sa.Float(), nullable=True))
    op.drop_column("prediction_history", "ht_goals_markets")
    op.drop_column("prediction_history", "goals_markets")
