"""corners and cards markets as multi-line JSON

Revision ID: 54ea77c61da2
Revises: 5cbfae8e7544
Create Date: 2026-09-23 15:54:54.762274

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "54ea77c61da2"
down_revision: str | None = "5cbfae8e7544"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # nullable=True (not autogenerate's default False): existing rows have
    # no value for these new columns and no server-side default is set, so
    # a NOT NULL add would fail against a table that already has rows (the
    # ORM model's `default=list` is a Python-side default for new objects,
    # not a DB-level one). Existing rows simply read back as an empty list
    # via SQLAlchemy's `default=list` until they're next re-predicted.
    op.add_column("prediction_history", sa.Column("corners_markets", sa.JSON(), nullable=True))
    op.add_column("prediction_history", sa.Column("cards_markets", sa.JSON(), nullable=True))
    op.drop_column("prediction_history", "prob_corners_under")
    op.drop_column("prediction_history", "prob_corners_over")
    op.drop_column("prediction_history", "prob_cards_under")
    op.drop_column("prediction_history", "prob_cards_over")
    op.add_column("predictions", sa.Column("corners_markets", sa.JSON(), nullable=True))
    op.add_column("predictions", sa.Column("cards_markets", sa.JSON(), nullable=True))
    op.drop_column("predictions", "prob_corners_under")
    op.drop_column("predictions", "prob_corners_over")
    op.drop_column("predictions", "prob_cards_under")
    op.drop_column("predictions", "prob_cards_over")


def downgrade() -> None:
    op.add_column("predictions", sa.Column("prob_cards_over", sa.Float(), nullable=True))
    op.add_column("predictions", sa.Column("prob_cards_under", sa.Float(), nullable=True))
    op.add_column("predictions", sa.Column("prob_corners_over", sa.Float(), nullable=True))
    op.add_column("predictions", sa.Column("prob_corners_under", sa.Float(), nullable=True))
    op.drop_column("predictions", "cards_markets")
    op.drop_column("predictions", "corners_markets")
    op.add_column("prediction_history", sa.Column("prob_cards_over", sa.Float(), nullable=True))
    op.add_column("prediction_history", sa.Column("prob_cards_under", sa.Float(), nullable=True))
    op.add_column("prediction_history", sa.Column("prob_corners_over", sa.Float(), nullable=True))
    op.add_column("prediction_history", sa.Column("prob_corners_under", sa.Float(), nullable=True))
    op.drop_column("prediction_history", "cards_markets")
    op.drop_column("prediction_history", "corners_markets")
