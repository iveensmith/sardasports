"""match tournament

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-10-08

Which tournament a tennis match belongs to, so a day's matches can be grouped by event.
Idempotent: a database created from the models already has the column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("matches")}
    if "tournament" not in columns:
        op.add_column("matches", sa.Column("tournament", sa.String(120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("matches") as batch:
        batch.drop_column("tournament")
