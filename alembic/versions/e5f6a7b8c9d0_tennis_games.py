"""tennis: total games won, separate from the set score

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-28

Tennis is won on sets, not games — a player can win fewer games and still
win the match. On the ingested ATP/WTA data a games-based winner label would
be wrong for 2.00% of matches and undefined (an exact games tie) for another
2.82%: 4.81% corrupted labels.

So `home_score`/`away_score` hold **sets** for tennis, which keeps "the
higher score won" true across every sport, and total games move into their
own nullable columns to price the total-games market.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("home_games", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("away_games", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "away_games")
    op.drop_column("matches", "home_games")
