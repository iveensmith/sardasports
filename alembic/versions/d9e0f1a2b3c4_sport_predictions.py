"""sport predictions

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-10-08

Basketball and tennis predictions stored before the match, so they can be graded.
Idempotent: a database created from the models already has the table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("sport_predictions"):
        return
    op.create_table(
        "sport_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("sport", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("home_win_pct", sa.Float(), nullable=False),
        sa.Column("away_win_pct", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("total_line", sa.Float(), nullable=True),
        sa.Column("prob_over_pct", sa.Float(), nullable=True),
        sa.Column("expected_total", sa.Float(), nullable=True),
        sa.Column("model_version", sa.String(40), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_sport_predictions_match_id", "sport_predictions", ["match_id"], unique=True)
    op.create_index("ix_sport_predictions_sport", "sport_predictions", ["sport"])
    op.create_index("ix_sport_predictions_created_at", "sport_predictions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sport_predictions_created_at", table_name="sport_predictions")
    op.drop_index("ix_sport_predictions_sport", table_name="sport_predictions")
    op.drop_index("ix_sport_predictions_match_id", table_name="sport_predictions")
    op.drop_table("sport_predictions")
