"""match live score

Revision ID: a1b2c3d4e5f6
Revises: e0f1a2b3c4d5
Create Date: 2026-10-10

A fixture's in-play view (status, minute, score), kept apart from home_score/away_score, which
mean "the final result" everywhere. Idempotent: a database created from the models already has
the columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "e0f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = [
    ("live_status", sa.String(8)),
    ("live_minute", sa.Integer()),
    ("live_home", sa.Integer()),
    ("live_away", sa.Integer()),
    ("live_updated_at", sa.DateTime()),
]


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("matches")}
    for name, kind in COLUMNS:
        if name not in existing:
            op.add_column("matches", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("matches") as batch:
        for name, _kind in COLUMNS:
            batch.drop_column(name)
