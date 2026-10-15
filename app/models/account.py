"""Member accounts: users, their sessions, one-time tokens, outgoing mail and an audit trail.

Everything secret is stored as a hash, never as the value: a password is a salted scrypt hash, and
a session or e-mail token is stored as the SHA-256 of a random value that only the member's browser
or inbox ever holds. A copy of this table is therefore not a set of working logins.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

ROLE_MEMBER = "member"
ROLE_ADMIN = "admin"

TOKEN_VERIFY_EMAIL = "verify_email"
TOKEN_RESET_PASSWORD = "reset_password"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored lower-cased, so "A@x.com" and "a@x.com" are one account.
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=ROLE_MEMBER, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Set when the link in the verification e-mail was used.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # When the member confirmed they are 18 or over. Sign-up cannot complete without it.
    over_18_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # The version of the Terms accepted (a date string), so a later change can ask again.
    terms_accepted_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Optional, and only ever set by the member: whether to receive the e-mail digest.
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


class AuthSession(Base):
    """One signed-in browser. The cookie holds a random value; only its hash is kept."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # A short description of the browser, so "log out my other devices" is recognisable.
    user_agent: Mapped[str | None] = mapped_column(String(160), nullable=True)


class AuthToken(Base):
    """A single-use token e-mailed to a member: verify an address, or reset a password."""

    __tablename__ = "auth_tokens"
    __table_args__ = (Index("ix_auth_tokens_user_kind", "user_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EmailOutbox(Base):
    """Every e-mail the site means to send.

    Written first, sent after: a mail provider outage never loses a verification link, and
    until SMTP is configured the owner can read the links here and pass them on by hand.
    """

    __tablename__ = "email_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    to_address: Mapped[str] = mapped_column(String(254), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)


class AuditLog(Base):
    """Who changed what: every administrator action that alters content or access."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    target: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
