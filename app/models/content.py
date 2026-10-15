"""Editorial content: blog posts and the administrator's own predictions.

The engine's predictions are computed and stored by the pipeline. The administrator can also
publish picks by hand ("editor's picks"). Those live in their own table and their own record, and
are never mixed into the engine's numbers: a human's pick and a model's pick are different claims.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

FORMAT_HTML = "html"
FORMAT_MARKDOWN = "markdown"

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"

RESULT_PENDING = "pending"
RESULT_WON = "won"
RESULT_LOST = "lost"
RESULT_VOID = "void"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    excerpt: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    # `html`: written in the rich-text editor and sanitised on save (app/services/html_sanitize),
    # so it is shown as stored. `markdown`: the earlier format, rendered by the website with a
    # small safe subset. Existing posts keep `markdown`; new ones are `html`.
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    body_format: Mapped[str] = mapped_column(
        String(10), default=FORMAT_HTML, server_default=FORMAT_MARKDOWN, nullable=False
    )
    category: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    # Comma-separated, at most a handful, no commas inside one.
    tags: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    # File name of the featured image (see app/services/media_service.py), not a path.
    featured_image: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default=STATUS_DRAFT, nullable=False)
    # Members with an active premium plan can read it; everyone else sees the excerpt.
    premium_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class ManualPick(Base):
    """A prediction written by the administrator.

    **Integrity rule:** a published pick cannot be edited, and cannot be deleted once its match
    has kicked off. Before kick-off the administrator may still delete it (a pick posted by
    mistake); after, it stays on the record and can only be marked void with a reason. A pick
    that could vanish after the result would let a record be curated.
    """

    __tablename__ = "manual_picks"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport: Mapped[str] = mapped_column(String(20), default="football", nullable=False)
    competition: Mapped[str] = mapped_column(String(120), nullable=False)
    home_team: Mapped[str] = mapped_column(String(120), nullable=False)
    away_team: Mapped[str] = mapped_column(String(120), nullable=False)
    kickoff: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # What is being picked: a market and a selection, in words ("Over 2.5 goals").
    market: Mapped[str] = mapped_column(String(80), nullable=False)
    selection: Mapped[str] = mapped_column(String(120), nullable=False)
    odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The editor's own confidence, 1 to 100, if they want to state one.
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)

    premium_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default=STATUS_DRAFT, nullable=False)
    result: Mapped[str] = mapped_column(String(10), default=RESULT_PENDING, nullable=False)
    void_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
