"""tennis: best-of format (3 or 5 sets)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-28

The match format roughly caps total games, and the tours differ: WTA is
always best-of-3 (21.8 total games on average across the ingested data)
while ATP plays best-of-5 at Grand Slams (25.9 overall). Without this the
total-games model would price a men's Slam like an ordinary tour match.
Nullable: football and basketball rows have no such notion.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("best_of", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "best_of")
