"""accounts, content and premium tables

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a7
Create Date: 2026-10-14

Member accounts (users, sessions, e-mail tokens, the outgoing-mail outbox, an audit log), the
administrator's content (blog posts and hand-written picks) and premium membership (plans,
subscriptions and payment events). Idempotent: each table is created only if it is missing,
using the same definitions the application uses, so there is one source of truth.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b9"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "users",
    "auth_sessions",
    "auth_tokens",
    "email_outbox",
    "audit_log",
    "posts",
    "manual_picks",
    "plans",
    "subscriptions",
    "payment_events",
)


def upgrade() -> None:
    import app.models  # noqa: F401 - registers every model on Base.metadata
    from app.database.base import Base

    bind = op.get_bind()
    for name in TABLES:  # dependency order: users before the tables that point at it
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for name in reversed(TABLES):
        if inspector.has_table(name):
            op.drop_table(name)
