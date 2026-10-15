"""Premium membership: plans, subscriptions and the payment events that drive them.

No card data is ever stored. Payment happens on the provider's own hosted page; this side keeps
only what is needed to know whether a member's access is paid for, and a record of the provider's
notifications (each stored once, so a repeated notification cannot be applied twice).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

SUB_ACTIVE = "active"
SUB_PAST_DUE = "past_due"
SUB_CANCELLED = "cancelled"
SUB_EXPIRED = "expired"


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    # A short stable name used in links and webhooks ("monthly", "yearly").
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    # In the currency's smallest unit (pence, kobo, cents): never a float.
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # How long one payment buys: "month" or "year".
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    # Only plans marked active are offered; the owner switches one on when it is ready.
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default=SUB_ACTIVE, nullable=False)
    # Access runs to this moment. Paying again moves it forward.
    current_period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # "stripe", "paystack" or "manual" (granted by the administrator).
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PaymentEvent(Base):
    """One notification from a payment provider, kept so it can only be applied once."""

    __tablename__ = "payment_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_payment_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
