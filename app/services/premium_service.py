"""Premium membership: who has access, how access is bought or granted, and when it ends.

Access is "a subscription row whose period has not ended". One payment buys one period (a month
or a year); paying again extends from the later of now and the current end. Nothing here renews by
itself, so there is never a charge a member did not knowingly make; a reminder e-mail before a
period ends is the renewal path.

Every payment notification is stored once by its provider id and applied once: a provider that
sends the same event twice (they do) extends access once.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.account import AuditLog, User
from app.models.premium import (
    SUB_ACTIVE,
    SUB_CANCELLED,
    PaymentEvent,
    Plan,
    Subscription,
)

INTERVAL_DAYS = {"month": 31, "year": 366}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def active_subscription(db: Session, user_id: int) -> Subscription | None:
    now = _now()
    return (
        db.query(Subscription)
        .filter(
            Subscription.user_id == user_id,
            Subscription.status.in_([SUB_ACTIVE, SUB_CANCELLED]),
            Subscription.current_period_end > now,
        )
        .order_by(Subscription.current_period_end.desc())
        .first()
    )


def has_premium(db: Session, user: User | None) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    return active_subscription(db, user.id) is not None


def entitlement(db: Session, user: User | None) -> dict:
    """What the website needs to know about a member's access."""
    if user is None:
        return {"premium": False, "until": None, "provider": None, "cancel_at_period_end": False}
    if user.is_admin:
        return {"premium": True, "until": None, "provider": "admin", "cancel_at_period_end": False}
    sub = active_subscription(db, user.id)
    if sub is None:
        return {"premium": False, "until": None, "provider": None, "cancel_at_period_end": False}
    return {
        "premium": True,
        "until": sub.current_period_end.isoformat(),
        "provider": sub.provider,
        "cancel_at_period_end": sub.cancel_at_period_end,
    }


# --- plans --------------------------------------------------------------------------------


def plan_view(plan: Plan) -> dict:
    return {
        "code": plan.code,
        "name": plan.name,
        "description": plan.description,
        "price_minor": plan.price_minor,
        "currency": plan.currency,
        "interval": plan.interval,
        "active": plan.active,
    }


def active_plans(db: Session) -> list[Plan]:
    return db.query(Plan).filter(Plan.active.is_(True)).order_by(Plan.price_minor.asc()).all()


def save_plan(
    db: Session,
    *,
    code: str,
    name: str,
    description: str,
    price_minor: int,
    currency: str,
    interval: str,
    active: bool,
) -> Plan:
    code = code.strip().lower()
    if not code or not code.replace("-", "").replace("_", "").isalnum():
        raise ValueError("The plan code can use letters, numbers, - and _ only.")
    if interval not in INTERVAL_DAYS:
        raise ValueError("The interval must be 'month' or 'year'.")
    if price_minor <= 0:
        raise ValueError("The price must be more than zero.")
    currency = currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("The currency is a three-letter code such as GBP, NGN or USD.")
    plan = db.query(Plan).filter(Plan.code == code).first()
    if plan is None:
        plan = Plan(code=code)
        db.add(plan)
    plan.name = name.strip()[:80]
    plan.description = description.strip()[:300]
    plan.price_minor = int(price_minor)
    plan.currency = currency
    plan.interval = interval
    plan.active = bool(active)
    db.flush()
    return plan


# --- granting and applying payments -------------------------------------------------------


def _extend(
    db: Session, user_id: int, plan: Plan | None, days: int, provider: str, ref: str | None
):
    now = _now()
    current = active_subscription(db, user_id)
    start = current.current_period_end if current is not None else now
    end = start + timedelta(days=days)
    if current is not None:
        current.current_period_end = end
        current.status = SUB_ACTIVE
        current.cancel_at_period_end = False
        current.updated_at = now
        if plan is not None:
            current.plan_id = plan.id
        if ref:
            current.provider_ref = ref
        return current
    sub = Subscription(
        user_id=user_id,
        plan_id=plan.id if plan is not None else None,
        status=SUB_ACTIVE,
        current_period_end=end,
        provider=provider,
        provider_ref=ref,
    )
    db.add(sub)
    db.flush()
    return sub


def grant_manually(
    db: Session, *, user: User, days: int, actor_id: int | None, note: str = ""
) -> Subscription:
    """The administrator gives a member premium for `days` days (a gift, a comp, a payment
    received outside the site). Audited."""
    if days <= 0 or days > 3660:
        raise ValueError("Enter a number of days between 1 and 3660.")
    sub = _extend(db, user.id, None, days, "manual", None)
    db.add(
        AuditLog(
            actor_id=actor_id,
            action="premium.grant",
            target=f"user:{user.id}",
            detail=f"{days} days. {note}".strip()[:300],
        )
    )
    return sub


def revoke(db: Session, *, user: User, actor_id: int | None) -> int:
    """End a member's premium now. Returns how many subscriptions were ended."""
    now = _now()
    ended = 0
    for sub in db.query(Subscription).filter(
        Subscription.user_id == user.id, Subscription.current_period_end > now
    ):
        sub.current_period_end = now
        sub.status = "expired"
        sub.updated_at = now
        ended += 1
    db.add(AuditLog(actor_id=actor_id, action="premium.revoke", target=f"user:{user.id}"))
    return ended


def apply_payment(
    db: Session,
    *,
    provider: str,
    event_id: str,
    kind: str,
    user_id: int | None,
    plan_code: str | None,
    amount_minor: int | None,
    currency: str | None,
    provider_ref: str | None,
) -> str:
    """Record one provider notification and, if it is a successful payment, extend access.

    Returns "applied", "duplicate" (seen before), or "ignored" (not a payment we act on, or it
    names a member or plan we do not have). Safe to call again with the same event.
    """
    event = PaymentEvent(
        provider=provider,
        event_id=event_id,
        kind=kind,
        user_id=user_id,
        amount_minor=amount_minor,
        currency=currency,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return "duplicate"

    plan = db.query(Plan).filter(Plan.code == (plan_code or "")).first()
    user = db.get(User, user_id) if user_id else None
    if user is None or plan is None:
        event.note = "unknown member or plan"
        db.commit()
        return "ignored"
    # The amount paid must be at least the plan's price: a notification that says otherwise
    # does not buy access (a changed price, or a forged or partial payment).
    if amount_minor is not None and amount_minor < plan.price_minor:
        event.note = f"paid {amount_minor} {currency}, plan costs {plan.price_minor}"
        db.commit()
        return "ignored"
    _extend(db, user.id, plan, INTERVAL_DAYS[plan.interval], provider, provider_ref)
    db.commit()
    return "applied"


def cancel_at_period_end(db: Session, user: User) -> bool:
    """Mark the member's access as not renewing. It simply runs out (nothing renews itself);
    this records the choice so the account page and reminders can say so."""
    sub = active_subscription(db, user.id)
    if sub is None:
        return False
    sub.cancel_at_period_end = True
    sub.status = SUB_CANCELLED
    sub.updated_at = _now()
    db.commit()
    return True
