"""Payment providers: start a hosted checkout, and check the provider's notifications.

Card details never reach this server: the member pays on the provider's own page, and the provider
tells this server, by a signed notification, that it was paid. So the two things that matter are
(1) that a notification really came from the provider (its signature, checked in constant time
against the secret only this server and the provider hold), and (2) that each is applied once
(see `premium_service.apply_payment`).

Only the provider whose secret is configured is offered. With none, a plan can still be granted by
the administrator.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

import requests

from app.models.account import User
from app.models.premium import Plan
from app.utils.config import get_settings

STRIPE_API = "https://api.stripe.com/v1"
PAYSTACK_API = "https://api.paystack.co"
TIMEOUT = 20


class PaymentError(Exception):
    pass


def configured_providers() -> list[str]:
    settings = get_settings()
    out = []
    if settings.stripe_secret_key:
        out.append("stripe")
    if settings.paystack_secret_key:
        out.append("paystack")
    return out


def _site(path: str) -> str:
    base = get_settings().public_site_url.rstrip("/")
    return f"{base}{path}"


# --- Stripe -------------------------------------------------------------------------------


def stripe_checkout(user: User, plan: Plan) -> str:
    """A Checkout Session for one payment of the plan's price. Returns the page to send the
    member to."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise PaymentError("Stripe is not configured.")
    fields = {
        "mode": "payment",
        "customer_email": user.email,
        "client_reference_id": str(user.id),
        "success_url": _site("/account?premium=thanks"),
        "cancel_url": _site("/premium?cancelled=1"),
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": plan.currency.lower(),
        "line_items[0][price_data][unit_amount]": str(plan.price_minor),
        "line_items[0][price_data][product_data][name]": f"SARDASPORTS {plan.name}",
        "metadata[user_id]": str(user.id),
        "metadata[plan_code]": plan.code,
    }
    response = requests.post(
        f"{STRIPE_API}/checkout/sessions",
        data=fields,
        auth=(settings.stripe_secret_key, ""),
        timeout=TIMEOUT,
    )
    if response.status_code >= 400:
        raise PaymentError("The payment provider refused to start the checkout.")
    url = response.json().get("url")
    if not url:
        raise PaymentError("The payment provider did not return a checkout address.")
    return url


def verify_stripe_signature(
    payload: bytes, header: str | None, secret: str, tolerance: int = 300, now: float | None = None
) -> bool:
    """Stripe signs `"{timestamp}.{body}"` with HMAC-SHA256 and sends `t=...,v1=...`.
    A timestamp older than `tolerance` seconds is refused, so a captured notification cannot be
    replayed later."""
    if not header or not secret:
        return False
    items = [item.split("=", 1) for item in header.split(",") if "=" in item]
    timestamp = next((value for key, value in items if key.strip() == "t"), None)
    given = [value for key, value in items if key.strip() == "v1"]
    if not timestamp or not given:
        return False
    try:
        age = abs((now if now is not None else time.time()) - int(timestamp))
    except ValueError:
        return False
    if age > tolerance:
        return False
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in given)


def parse_stripe_event(payload: bytes) -> dict | None:
    """Reduce a Stripe event to what `apply_payment` needs, or None if it is not a payment."""
    event = json.loads(payload)
    if event.get("type") != "checkout.session.completed":
        return None
    obj = (event.get("data") or {}).get("object") or {}
    if obj.get("payment_status") != "paid":
        return None
    meta = obj.get("metadata") or {}
    try:
        user_id = int(meta.get("user_id") or obj.get("client_reference_id"))
    except (TypeError, ValueError):
        user_id = None
    return {
        "event_id": event.get("id", ""),
        "kind": event.get("type", ""),
        "user_id": user_id,
        "plan_code": meta.get("plan_code"),
        "amount_minor": obj.get("amount_total"),
        "currency": (obj.get("currency") or "").upper() or None,
        "provider_ref": obj.get("id"),
    }


# --- Paystack -----------------------------------------------------------------------------


def paystack_checkout(user: User, plan: Plan) -> str:
    settings = get_settings()
    if not settings.paystack_secret_key:
        raise PaymentError("Paystack is not configured.")
    body = {
        "email": user.email,
        "amount": plan.price_minor,
        "currency": plan.currency,
        "reference": f"sd-{user.id}-{uuid.uuid4().hex[:12]}",
        "callback_url": _site("/account?premium=thanks"),
        "metadata": {"user_id": user.id, "plan_code": plan.code},
    }
    response = requests.post(
        f"{PAYSTACK_API}/transaction/initialize",
        json=body,
        headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
        timeout=TIMEOUT,
    )
    if response.status_code >= 400:
        raise PaymentError("The payment provider refused to start the checkout.")
    url = ((response.json().get("data")) or {}).get("authorization_url")
    if not url:
        raise PaymentError("The payment provider did not return a checkout address.")
    return url


def verify_paystack_signature(payload: bytes, header: str | None, secret: str) -> bool:
    """Paystack sends HMAC-SHA512 of the raw body, keyed with the secret key."""
    if not header or not secret:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, header)


def parse_paystack_event(payload: bytes) -> dict | None:
    event = json.loads(payload)
    if event.get("event") != "charge.success":
        return None
    data = event.get("data") or {}
    if data.get("status") != "success":
        return None
    meta = data.get("metadata") or {}
    try:
        user_id = int(meta.get("user_id"))
    except (TypeError, ValueError):
        user_id = None
    reference = str(data.get("reference") or data.get("id") or "")
    return {
        "event_id": reference,
        "kind": "charge.success",
        "user_id": user_id,
        "plan_code": meta.get("plan_code"),
        "amount_minor": data.get("amount"),
        "currency": (data.get("currency") or "").upper() or None,
        "provider_ref": reference,
    }
