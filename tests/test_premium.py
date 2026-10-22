"""Premium: plans, checkout, signed provider notifications, and applying each payment once."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.models.account import ROLE_ADMIN, User
from app.models.premium import PaymentEvent, Plan, Subscription
from app.services import auth_service, payments, premium_service
from app.services.auth_service import hash_password
from app.utils.config import get_settings

PASSWORD = "correct-horse-battery"


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _fresh_limits():
    auth_service.reset_rate_limits()
    yield
    auth_service.reset_rate_limits()


@pytest.fixture
def settings_for_payments(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
    monkeypatch.setattr(settings, "paystack_secret_key", "sk_paystack")
    monkeypatch.setattr(settings, "public_site_url", "https://sardasports.example")
    return settings


def _user(db_session, email="member@example.com", role="member", verified=True):
    user = User(
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
        email_verified_at=_now() if verified else None,
        over_18_confirmed_at=_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


def _plan(db_session, code="monthly", price=500000, currency="NGN", interval="month", active=True):
    plan = Plan(
        code=code,
        name="Monthly",
        price_minor=price,
        currency=currency,
        interval=interval,
        active=active,
    )
    db_session.add(plan)
    db_session.commit()
    return plan


def _headers(client, email="member@example.com"):
    token = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _stripe_header(payload: bytes, secret="whsec_test", timestamp=None):
    ts = str(int(timestamp if timestamp is not None else time.time()))
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _stripe_event(user_id, plan_code="monthly", amount=500000, event_id="evt_1", paid="paid"):
    return json.dumps(
        {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_1",
                    "payment_status": paid,
                    "amount_total": amount,
                    "currency": "ngn",
                    "metadata": {"user_id": str(user_id), "plan_code": plan_code},
                }
            },
        }
    ).encode()


def _paystack_event(user_id, plan_code="monthly", amount=500000, reference="sd-1-abc"):
    return json.dumps(
        {
            "event": "charge.success",
            "data": {
                "status": "success",
                "reference": reference,
                "amount": amount,
                "currency": "NGN",
                "metadata": {"user_id": user_id, "plan_code": plan_code},
            },
        }
    ).encode()


# --- signatures ---------------------------------------------------------------------------


def test_a_stripe_notification_needs_a_valid_fresh_signature():
    payload = b'{"id":"evt"}'
    good = _stripe_header(payload)

    assert payments.verify_stripe_signature(payload, good, "whsec_test")
    assert not payments.verify_stripe_signature(payload + b"x", good, "whsec_test")
    assert not payments.verify_stripe_signature(payload, good, "another-secret")
    assert not payments.verify_stripe_signature(payload, None, "whsec_test")
    assert not payments.verify_stripe_signature(payload, "garbage", "whsec_test")
    # Replayed long after it was signed.
    old = _stripe_header(payload, timestamp=time.time() - 3600)
    assert not payments.verify_stripe_signature(payload, old, "whsec_test")


def test_a_paystack_notification_needs_a_valid_signature():
    payload = b'{"event":"charge.success"}'
    sig = hmac.new(b"sk_paystack", payload, hashlib.sha512).hexdigest()

    assert payments.verify_paystack_signature(payload, sig, "sk_paystack")
    assert not payments.verify_paystack_signature(payload + b" ", sig, "sk_paystack")
    assert not payments.verify_paystack_signature(payload, "0" * 128, "sk_paystack")
    assert not payments.verify_paystack_signature(payload, sig, "")


# --- webhooks -----------------------------------------------------------------------------


def test_a_signed_stripe_payment_grants_access_once(client, db_session, settings_for_payments):
    user = _user(db_session)
    _plan(db_session)
    payload = _stripe_event(user.id)
    headers = {"Stripe-Signature": _stripe_header(payload)}

    first = client.post("/premium/webhook/stripe", content=payload, headers=headers)
    again = client.post("/premium/webhook/stripe", content=payload, headers=headers)

    assert first.json()["result"] == "applied"
    assert again.json()["result"] == "duplicate"
    db_session.expire_all()
    subs = db_session.query(Subscription).all()
    assert len(subs) == 1  # a repeated notification extends access once
    assert subs[0].current_period_end > _now() + timedelta(days=28)
    assert subs[0].current_period_end < _now() + timedelta(days=33)
    assert db_session.query(PaymentEvent).count() == 1


def test_an_unsigned_or_forged_notification_grants_nothing(
    client, db_session, settings_for_payments
):
    user = _user(db_session)
    _plan(db_session)
    payload = _stripe_event(user.id)

    unsigned = client.post("/premium/webhook/stripe", content=payload)
    forged = client.post(
        "/premium/webhook/stripe",
        content=payload,
        headers={"Stripe-Signature": _stripe_header(payload, secret="not-the-secret")},
    )

    assert unsigned.status_code == 400 and forged.status_code == 400
    assert db_session.query(Subscription).count() == 0


def test_a_payment_below_the_plan_price_does_not_buy_access(
    client, db_session, settings_for_payments
):
    user = _user(db_session)
    _plan(db_session, price=500000)
    payload = _stripe_event(user.id, amount=100)

    response = client.post(
        "/premium/webhook/stripe",
        content=payload,
        headers={"Stripe-Signature": _stripe_header(payload)},
    )

    assert response.json()["result"] == "ignored"
    assert db_session.query(Subscription).count() == 0


def test_an_unpaid_checkout_session_is_not_a_payment(client, db_session, settings_for_payments):
    user = _user(db_session)
    _plan(db_session)
    payload = _stripe_event(user.id, paid="unpaid")

    response = client.post(
        "/premium/webhook/stripe",
        content=payload,
        headers={"Stripe-Signature": _stripe_header(payload)},
    )

    assert response.json()["result"] == "ignored"
    assert db_session.query(Subscription).count() == 0


def test_a_signed_paystack_payment_grants_access(client, db_session, settings_for_payments):
    user = _user(db_session)
    _plan(db_session)
    payload = _paystack_event(user.id)
    sig = hmac.new(b"sk_paystack", payload, hashlib.sha512).hexdigest()

    response = client.post(
        "/premium/webhook/paystack", content=payload, headers={"x-paystack-signature": sig}
    )

    assert response.json()["result"] == "applied"
    db_session.expire_all()
    assert premium_service.has_premium(db_session, db_session.get(User, user.id))


def test_paying_again_extends_from_the_end_of_the_current_period(db_session):
    user = _user(db_session)
    plan = _plan(db_session)

    premium_service.apply_payment(
        db_session,
        provider="stripe",
        event_id="e1",
        kind="x",
        user_id=user.id,
        plan_code=plan.code,
        amount_minor=plan.price_minor,
        currency="NGN",
        provider_ref="r1",
    )
    first_end = db_session.query(Subscription).one().current_period_end
    premium_service.apply_payment(
        db_session,
        provider="stripe",
        event_id="e2",
        kind="x",
        user_id=user.id,
        plan_code=plan.code,
        amount_minor=plan.price_minor,
        currency="NGN",
        provider_ref="r2",
    )

    db_session.expire_all()
    sub = db_session.query(Subscription).one()  # still one subscription
    assert sub.current_period_end - first_end == timedelta(days=31)


# --- entitlement --------------------------------------------------------------------------


def test_access_ends_when_the_period_ends(db_session):
    user = _user(db_session)
    db_session.add(
        Subscription(
            user_id=user.id,
            status="active",
            provider="manual",
            current_period_end=_now() - timedelta(minutes=1),
        )
    )
    db_session.commit()

    assert premium_service.has_premium(db_session, user) is False


def test_an_administrator_always_has_access(db_session):
    admin = _user(db_session, "admin@example.com", role=ROLE_ADMIN)
    assert premium_service.has_premium(db_session, admin) is True
    assert premium_service.has_premium(db_session, None) is False


def test_cancelling_keeps_access_until_the_period_ends(client, db_session):
    user = _user(db_session)
    premium_service.grant_manually(db_session, user=user, days=30, actor_id=None)
    db_session.commit()
    headers = _headers(client)

    client.post("/premium/cancel", headers=headers)
    me = client.get("/auth/me", headers=headers).json()["entitlement"]

    assert me["premium"] is True and me["cancel_at_period_end"] is True


# --- plans and checkout -------------------------------------------------------------------


def test_only_active_plans_are_offered(client, db_session):
    _plan(db_session, code="monthly", active=True)
    _plan(db_session, code="draft-plan", active=False)

    body = client.get("/premium/plans").json()

    assert [p["code"] for p in body["plans"]] == ["monthly"]
    assert body["providers"] == []  # nothing is configured in the test environment


def test_checkout_says_payments_are_unavailable_when_no_provider_is_set(client, db_session):
    _user(db_session)
    _plan(db_session)

    response = client.post(
        "/premium/checkout", json={"plan_code": "monthly"}, headers=_headers(client)
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "payments_unavailable"


def test_checkout_needs_a_signed_in_verified_member(client, db_session, settings_for_payments):
    _plan(db_session)
    _user(db_session, "unverified@example.com", verified=False)

    anonymous = client.post("/premium/checkout", json={"plan_code": "monthly"})

    assert anonymous.status_code == 401


def test_checkout_starts_a_hosted_payment(client, db_session, settings_for_payments, monkeypatch):
    _user(db_session)
    _plan(db_session)
    seen = {}

    class Response:
        status_code = 200

        def json(self):
            return {"url": "https://checkout.stripe.example/pay/cs_1"}

    def fake_post(url, **kwargs):
        seen["url"], seen["kwargs"] = url, kwargs
        return Response()

    monkeypatch.setattr(payments.requests, "post", fake_post)

    response = client.post(
        "/premium/checkout",
        json={"plan_code": "monthly", "provider": "stripe"},
        headers=_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["url"].startswith("https://checkout.stripe.example/")
    fields = seen["kwargs"]["data"]
    assert fields["metadata[plan_code]"] == "monthly"
    assert fields["line_items[0][price_data][unit_amount]"] == "500000"
    # No card data is ever handled here: the member pays on the provider's page.
    assert "card" not in json.dumps(fields).lower()


def test_plans_can_be_created_by_the_admin_only(client, db_session):
    _user(db_session, "admin@example.com", role=ROLE_ADMIN)
    _user(db_session, "member@example.com")
    body = {
        "code": "yearly",
        "name": "Yearly",
        "price_minor": 4000000,
        "currency": "ngn",
        "interval": "year",
        "active": True,
    }

    denied = client.post("/admin/plans", json=body, headers=_headers(client, "member@example.com"))
    allowed = client.post("/admin/plans", json=body, headers=_headers(client, "admin@example.com"))

    assert denied.status_code == 403
    assert allowed.status_code == 200 and allowed.json()["plan"]["currency"] == "NGN"
    assert [p["code"] for p in client.get("/premium/plans").json()["plans"]] == ["yearly"]


def test_a_plan_needs_sensible_values(client, db_session):
    _user(db_session, "admin@example.com", role=ROLE_ADMIN)
    headers = _headers(client, "admin@example.com")
    base = {"code": "x", "name": "X", "price_minor": 100, "currency": "GBP", "interval": "month"}

    assert (
        client.post(
            "/admin/plans", json={**base, "interval": "fortnight"}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/admin/plans", json={**base, "currency": "POUNDS"}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post("/admin/plans", json={**base, "price_minor": 0}, headers=headers).status_code
        == 422
    )


def _pay(db_session, user, plan, event_id):
    premium_service.apply_payment(
        db_session,
        provider="stripe",
        event_id=event_id,
        kind="x",
        user_id=user.id,
        plan_code=plan.code,
        amount_minor=plan.price_minor,
        currency=plan.currency,
        provider_ref=event_id,
    )


def test_each_interval_buys_its_own_length_of_access(db_session):
    for code, interval, days in (
        ("weekly", "week", 7),
        ("monthly", "month", 31),
        ("yearly", "year", 366),
    ):
        user = _user(db_session, f"{code}@example.com")
        plan = _plan(db_session, code=code, price=1099, currency="USD", interval=interval)

        _pay(db_session, user, plan, f"pay-{code}")

        db_session.expire_all()
        sub = db_session.query(Subscription).filter(Subscription.user_id == user.id).one()
        left = sub.current_period_end - _now()
        assert timedelta(days=days - 1) < left <= timedelta(days=days)
