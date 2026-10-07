"""A message sent through the Contact page.

Deliberately minimal: what is needed to read and answer the message, and nothing
else. No IP address and no user agent are stored (the rate limit that guards the
form lives in memory and is never written down), so the privacy policy can say
plainly what is kept.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    topic: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Set when the operator has dealt with it, so the unread list stays short.
    handled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
