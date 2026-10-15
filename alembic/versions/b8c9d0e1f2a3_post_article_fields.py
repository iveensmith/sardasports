"""blog posts: rich-text body, category, tags and a featured image

Revision ID: b8c9d0e1f2a3
Revises: c3d4e5f6a7b9
Create Date: 2026-10-15

Posts were Markdown. The editor is now a rich-text one, so a post records which format its body is
in (existing posts stay `markdown` and are still rendered as before; new ones are `html`), plus the
category, comma-separated tags and the featured image's file name.

Idempotent: a column is added only if it is missing (a database first created from the current
models already has them).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "c3d4e5f6a7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "posts" not in inspector.get_table_names():
        return
    present = {column["name"] for column in inspector.get_columns("posts")}
    if "body_format" not in present:
        op.add_column(
            "posts",
            sa.Column("body_format", sa.String(10), nullable=False, server_default="markdown"),
        )
    if "category" not in present:
        op.add_column("posts", sa.Column("category", sa.String(60), nullable=True))
    if "tags" not in present:
        op.add_column("posts", sa.Column("tags", sa.String(500), nullable=False, server_default=""))
    if "featured_image" not in present:
        op.add_column("posts", sa.Column("featured_image", sa.String(80), nullable=True))


def downgrade() -> None:
    # SQLite cannot drop a column in place, and the new columns are harmless to older code, so
    # a downgrade leaves them. (A rebuild-and-copy would risk the one table that holds posts.)
    pass
