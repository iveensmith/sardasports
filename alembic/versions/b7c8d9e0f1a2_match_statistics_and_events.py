"""match statistics (possession, offsides, fouls) and goal events

Revision ID: b7c8d9e0f1a2
Revises: a7b8c9d0e1f2
Create Date: 2026-09-30

Shots, shots on target, corners and cards already had columns (filled for
the historical Football-Data.co.uk training data), but nothing fetched them
for a live match this engine had already predicted — `fetch_results.py`
deliberately fetches only the score, flagging statistics as "a deliberate
follow-up, not an oversight." This is that follow-up: three more actual-stat
columns (possession, offsides, fouls — the ones the historical data never
had either, so there was nowhere to put them before now), and a table for
the goals themselves.

`match_events` is its own table rather than a JSON column because a reader
wants them in order with a running score, which is a query, not a blob to
parse client-side. Football only, and only ever synced from API-Football's
own `/fixtures/events` — no event is ever invented for a match the source
doesn't cover.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("home_possession", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("away_possession", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("home_offsides", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("away_offsides", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("home_fouls", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("away_fouls", sa.Integer(), nullable=True))
    # Set the moment `scripts/fetch_match_stats.py` has tried this fixture,
    # whether or not the response actually carried any statistics — some
    # competitions genuinely report none. Without this, a fixture with
    # nothing to fetch would look identical to one never attempted, and
    # every scheduled run would re-request it forever.
    op.add_column("matches", sa.Column("stats_fetched_at", sa.DateTime(), nullable=True))

    op.create_table(
        "match_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("added_time", sa.Integer(), nullable=True),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("player", sa.String(120), nullable=False),
        sa.Column("assist", sa.String(120), nullable=True),
        sa.Column("detail", sa.String(40), nullable=False),
        sa.Column("home_score_after", sa.Integer(), nullable=False),
        sa.Column("away_score_after", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False, server_default="api-football"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_match_events_match_id", "match_events", ["match_id"])


def downgrade() -> None:
    op.drop_index("ix_match_events_match_id", table_name="match_events")
    op.drop_table("match_events")

    op.drop_column("matches", "stats_fetched_at")
    op.drop_column("matches", "away_fouls")
    op.drop_column("matches", "home_fouls")
    op.drop_column("matches", "away_offsides")
    op.drop_column("matches", "home_offsides")
    op.drop_column("matches", "away_possession")
    op.drop_column("matches", "home_possession")
