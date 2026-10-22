"""Premium membership: plans, checkout, cancellation and the providers' notifications."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps_auth import current_user, fail
from app.database.session import get_db
from app.models.account import User
from app.models.premium import Plan
from app.services import payments, premium_rows, premium_service
from app.services.auth_service import AuthError
from app.utils.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/premium", tags=["premium"])


class CheckoutIn(BaseModel):
    plan_code: str = Field(max_length=40)
    provider: str | None = Field(default=None, max_length=20)


@router.get("/plans")
def plans(db: Session = Depends(get_db)) -> dict:
    """The plans on offer, and which ways of paying are switched on."""
    return {
        "plans": [premium_service.plan_view(p) for p in premium_service.active_plans(db)],
        "providers": payments.configured_providers(),
    }


@router.get("/rows")
def unlocked_rows(
    ids: str = Query("", description="Comma-separated match ids."),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Full board rows for a premium member: the predictions the public pages hide."""
    if not premium_service.entitlement(db, user)["premium"]:
        raise fail(AuthError("premium_required", "This is for premium members.", 403))
    return {"rows": premium_rows.rows_for_matches(db, premium_rows.parse_ids(ids))}


@router.post("/checkout")
def checkout(
    body: CheckoutIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    if not user.email_verified:
        raise fail(AuthError("not_verified", "Confirm your e-mail address before paying.", 403))
    plan = db.query(Plan).filter(Plan.code == body.plan_code, Plan.active.is_(True)).first()
    if plan is None:
        raise fail(AuthError("no_such_plan", "That plan is not available.", 404))
    available = payments.configured_providers()
    if not available:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "payments_unavailable",
                "message": "Online payment is not switched on yet. Please check back soon.",
            },
        )
    provider = body.provider if body.provider in available else available[0]
    try:
        url = (
            payments.stripe_checkout(user, plan)
            if provider == "stripe"
            else payments.paystack_checkout(user, plan)
        )
    except payments.PaymentError as error:
        logger.warning("checkout failed for user %s: %s", user.id, error)
        raise HTTPException(
            status_code=502,
            detail={"code": "provider_error", "message": "Could not start the payment. Try again."},
        ) from None
    return {"url": url, "provider": provider}


@router.post("/cancel")
def cancel(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    changed = premium_service.cancel_at_period_end(db, user)
    return {"ok": changed}


def _apply(db: Session, provider: str, event: dict | None) -> dict:
    if event is None:
        return {"ok": True, "result": "ignored"}
    result = premium_service.apply_payment(
        db,
        provider=provider,
        event_id=event["event_id"],
        kind=event["kind"],
        user_id=event["user_id"],
        plan_code=event["plan_code"],
        amount_minor=event["amount_minor"],
        currency=event["currency"],
        provider_ref=event["provider_ref"],
    )
    return {"ok": True, "result": result}


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    payload = await request.body()
    secret = get_settings().stripe_webhook_secret
    if not payments.verify_stripe_signature(payload, stripe_signature, secret):
        raise HTTPException(status_code=400, detail={"code": "bad_signature"})
    try:
        event = payments.parse_stripe_event(payload)
    except (ValueError, KeyError):
        raise HTTPException(status_code=400, detail={"code": "bad_payload"}) from None
    return _apply(db, "stripe", event)


@router.post("/webhook/paystack")
async def paystack_webhook(
    request: Request,
    x_paystack_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    payload = await request.body()
    secret = get_settings().paystack_secret_key
    if not payments.verify_paystack_signature(payload, x_paystack_signature, secret):
        raise HTTPException(status_code=400, detail={"code": "bad_signature"})
    try:
        event = payments.parse_paystack_event(payload)
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail={"code": "bad_payload"}) from None
    return _apply(db, "paystack", event)
