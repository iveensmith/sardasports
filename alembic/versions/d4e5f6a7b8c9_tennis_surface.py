"""tennis: per-match surface

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-09-28

`matches.surface` — "Hard"/"Clay"/"Grass"/"Carpet" for tennis, NULL for
football and basketball, following the same "genuinely not applicable rather
than zero/empty" rule as the corner and card columns.

Nullable by necessity as well as by design: 68,514 rows already exist and
none of them has a surface.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("surface", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "surface")
