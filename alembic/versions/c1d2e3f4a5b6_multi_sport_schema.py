"""multi-sport schema: sport discriminator, score rename, neutral venues

Revision ID: c1d2e3f4a5b6
Revises: ab73824e13f3
Create Date: 2026-09-28

Turns a football-only schema into a multi-sport one (see
docs/architecture.md's "Multi-sport schema" section):

- `matches.sport` / `teams.sport` discriminators, defaulting to "football"
  so every existing row keeps its meaning without a data backfill.
- `home_goals`/`away_goals` -> `home_score`/`away_score`. A *rename*, not a
  drop-and-add: these columns hold 62,568 real ingested matches, and
  add+drop would silently discard every one of them.
- `matches.neutral_venue`, because tournament football (World Cup, Euros)
  is played on neutral ground, where the Elo home-advantage offset and the
  Poisson home term are both wrong.
- `teams.name` loses its global UNIQUE in favour of UNIQUE(sport, name):
  the same string can legitimately name a football club and a basketball
  franchise, and merging their rating histories would be a real bug.

SQLite can't ALTER/DROP CONSTRAINT in place, so both tables go through
batch_alter_table (which rebuilds the table and copies the rows).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "ab73824e13f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("matches") as batch:
        # server_default so the NOT NULL is satisfiable for existing rows;
        # every row already in this table is football.
        batch.add_column(
            sa.Column("sport", sa.String(20), nullable=False, server_default="football")
        )
        batch.add_column(
            sa.Column("neutral_venue", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.alter_column("home_goals", new_column_name="home_score")
        batch.alter_column("away_goals", new_column_name="away_score")
    op.create_index("ix_matches_sport", "matches", ["sport"])

    with op.batch_alter_table("teams") as batch:
        batch.add_column(
            sa.Column("sport", sa.String(20), nullable=False, server_default="football")
        )
        batch.drop_index("ix_teams_name")
        batch.create_index("ix_teams_name", ["name"])
        batch.create_unique_constraint("uq_teams_sport_name", ["sport", "name"])
    op.create_index("ix_teams_sport", "teams", ["sport"])


def downgrade() -> None:
    op.drop_index("ix_teams_sport", table_name="teams")
    with op.batch_alter_table("teams") as batch:
        batch.drop_constraint("uq_teams_sport_name", type_="unique")
        batch.drop_index("ix_teams_name")
        batch.create_index("ix_teams_name", ["name"], unique=True)
        batch.drop_column("sport")

    op.drop_index("ix_matches_sport", table_name="matches")
    with op.batch_alter_table("matches") as batch:
        batch.alter_column("away_score", new_column_name="away_goals")
        batch.alter_column("home_score", new_column_name="home_goals")
        batch.drop_column("neutral_venue")
        batch.drop_column("sport")
