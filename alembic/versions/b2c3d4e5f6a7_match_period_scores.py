"""match period scores

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-11

Per-period scores (basketball quarters, tennis sets) in one JSON column, for the markets that
need them. Idempotent: a database created from the models already has the column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("matches")}
    if "period_scores" not in columns:
        op.add_column("matches", sa.Column("period_scores", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("matches") as batch:
        batch.drop_column("period_scores")
