"""Accounts: sign-up, e-mail verification, sign-in, sessions, reset and deletion.

What these protect: nobody can sign in without a verified address, nobody can learn whether an
address is registered, secrets are never stored in the clear, and deleting an account really
removes the member.
"""

from __future__ import annotations

import re

import pytest

from app.models.account import AuthSession, AuthToken, EmailOutbox, User
from app.services import auth_service

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def _fresh_limits():
    auth_service.reset_rate_limits()
    yield
    auth_service.reset_rate_limits()


def _register(client, email="member@example.com", password=PASSWORD, **over):
    body = {
        "email": email,
        "password": password,
        "over_18": True,
        "accept_terms": True,
    }
    body.update(over)
    return client.post("/auth/register", json=body)


def _token_from_mail(db_session, kind):
    db_session.expire_all()
    mail = (
        db_session.query(EmailOutbox)
        .filter(EmailOutbox.kind == kind)
        .order_by(EmailOutbox.id.desc())
        .first()
    )
    assert mail is not None, f"no {kind} mail was written"
    found = re.search(r"token=([A-Za-z0-9_\-]+)", mail.body_text)
    assert found, mail.body_text
    return found.group(1)


def _verified_member(client, db_session, email="member@example.com"):
    assert _register(client, email).status_code == 200
    token = _token_from_mail(db_session, "verify_email")
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 200


def _login(client, email="member@example.com", password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


# --- sign-up ------------------------------------------------------------------------------


def test_sign_up_creates_an_unverified_member_and_mails_a_link(client, db_session):
    response = _register(client)

    assert response.status_code == 200
    user = db_session.query(User).one()
    assert user.email == "member@example.com"
    assert user.email_verified_at is None
    assert user.over_18_confirmed_at is not None  # the confirmation is recorded with a date
    assert user.terms_accepted_version
    mail = db_session.query(EmailOutbox).one()
    assert mail.to_address == "member@example.com" and "token=" in mail.body_text


def test_the_password_is_stored_as_a_salted_hash(client, db_session):
    _register(client)

    stored = db_session.query(User).one().password_hash
    assert PASSWORD not in stored
    assert stored.startswith("scrypt$")
    assert auth_service.verify_password(PASSWORD, stored)
    assert not auth_service.verify_password("wrong-password-123", stored)
    # Two members with the same password get different hashes (a per-password salt).
    assert auth_service.hash_password(PASSWORD) != auth_service.hash_password(PASSWORD)


def test_sign_up_requires_age_confirmation_and_terms(client, db_session):
    no_age = _register(client, over_18=False)
    no_terms = _register(client, email="b@example.com", accept_terms=False)

    assert no_age.status_code == 400 and no_age.json()["detail"]["code"] == "age_required"
    assert no_terms.status_code == 400 and no_terms.json()["detail"]["code"] == "terms_required"
    assert db_session.query(User).count() == 0


@pytest.mark.parametrize("password", ["short", "password123", "aaaaaaaaaaaa", "x" * 200])
def test_weak_passwords_are_refused(client, db_session, password):
    response = _register(client, password=password)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "weak_password"
    assert db_session.query(User).count() == 0


def test_a_bad_address_is_refused(client):
    response = _register(client, email="not-an-address")
    assert response.status_code == 400 and response.json()["detail"]["code"] == "invalid_email"


def test_registering_a_known_address_answers_the_same_and_creates_nothing(client, db_session):
    first = _register(client)
    second = _register(client)

    assert first.json() == second.json()
    assert db_session.query(User).count() == 1
    kinds = [m.kind for m in db_session.query(EmailOutbox).order_by(EmailOutbox.id)]
    assert kinds == ["verify_email", "already_registered"]


def test_addresses_are_case_insensitive(client, db_session):
    _register(client, email="Member@Example.COM")
    _register(client, email="member@example.com")

    assert db_session.query(User).count() == 1


# --- verification -------------------------------------------------------------------------


def test_sign_in_is_refused_until_the_address_is_confirmed(client, db_session):
    _register(client)

    response = _login(client)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "not_verified"


def test_the_confirmation_link_works_once_and_then_sign_in_works(client, db_session):
    _register(client)
    token = _token_from_mail(db_session, "verify_email")

    first = client.post("/auth/verify-email", json={"token": token})
    again = client.post("/auth/verify-email", json={"token": token})
    signed_in = _login(client)

    assert first.status_code == 200
    assert again.status_code == 400 and again.json()["detail"]["code"] == "token_invalid"
    assert signed_in.status_code == 200 and signed_in.json()["token"]


def test_tokens_are_stored_hashed_not_in_the_clear(client, db_session):
    _register(client)
    token = _token_from_mail(db_session, "verify_email")

    stored = db_session.query(AuthToken).one()
    assert token not in stored.token_hash and len(stored.token_hash) == 64


def test_an_expired_confirmation_link_is_refused(client, db_session):
    from datetime import timedelta

    _register(client)
    token = _token_from_mail(db_session, "verify_email")
    row = db_session.query(AuthToken).one()
    row.expires_at = row.expires_at - timedelta(days=30)
    db_session.commit()

    response = client.post("/auth/verify-email", json={"token": token})

    assert response.status_code == 400 and response.json()["detail"]["code"] == "token_invalid"


def test_a_resent_link_replaces_the_old_one(client, db_session):
    _register(client)
    old = _token_from_mail(db_session, "verify_email")

    client.post("/auth/resend-verification", json={"email": "member@example.com"})
    new = _token_from_mail(db_session, "verify_email")

    assert old != new
    assert client.post("/auth/verify-email", json={"token": old}).status_code == 400
    assert client.post("/auth/verify-email", json={"token": new}).status_code == 200


# --- sign-in and sessions -----------------------------------------------------------------


def test_sign_in_returns_a_session_that_identifies_the_member(client, db_session):
    _verified_member(client, db_session)

    body = _login(client).json()
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"})

    assert me.status_code == 200
    assert me.json()["user"]["email"] == "member@example.com"
    assert me.json()["user"]["role"] == "member"
    assert me.json()["entitlement"]["premium"] is False
    # Only a hash of the session token is stored.
    assert db_session.query(AuthSession).one().token_hash != body["token"]


def test_a_wrong_password_and_an_unknown_address_look_the_same(client, db_session):
    _verified_member(client, db_session)

    wrong = _login(client, password="not-the-password-1")
    unknown = _login(client, email="nobody@example.com")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_a_missing_or_bad_session_is_not_signed_in(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_logout_ends_the_session(client, db_session):
    _verified_member(client, db_session)
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/auth/logout", headers=headers)

    assert client.get("/auth/me", headers=headers).status_code == 401


def test_repeated_wrong_passwords_are_rate_limited(client, db_session):
    _verified_member(client, db_session)

    codes = [_login(client, password=f"wrong-password-{i}").status_code for i in range(12)]

    assert 429 in codes
    # And even the right password is held back while the limit is on.
    assert _login(client).status_code == 429


def test_sign_up_attempts_are_rate_limited_per_address(client):
    codes = [_register(client, email="same@example.com").status_code for _ in range(6)]

    assert codes[:3] == [200, 200, 200] and 429 in codes


# --- password reset and change ------------------------------------------------------------


def test_reset_for_an_unknown_address_answers_like_a_known_one(client, db_session):
    _verified_member(client, db_session)

    known = client.post("/auth/forgot-password", json={"email": "member@example.com"})
    unknown = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert known.json() == unknown.json()
    assert db_session.query(EmailOutbox).filter_by(kind="reset_password").count() == 1


def test_a_reset_sets_the_new_password_and_signs_everyone_out(client, db_session):
    _verified_member(client, db_session)
    old_session = _login(client).json()["token"]
    client.post("/auth/forgot-password", json={"email": "member@example.com"})
    token = _token_from_mail(db_session, "reset_password")

    done = client.post(
        "/auth/reset-password", json={"token": token, "password": "a-brand-new-passphrase"}
    )

    assert done.status_code == 200
    assert (
        client.get("/auth/me", headers={"Authorization": f"Bearer {old_session}"}).status_code
        == 401
    )
    assert _login(client).status_code == 401  # the old password no longer works
    assert _login(client, password="a-brand-new-passphrase").status_code == 200


def test_a_reset_link_is_single_use(client, db_session):
    _verified_member(client, db_session)
    client.post("/auth/forgot-password", json={"email": "member@example.com"})
    token = _token_from_mail(db_session, "reset_password")
    payload = {"token": token, "password": "a-brand-new-passphrase"}

    assert client.post("/auth/reset-password", json=payload).status_code == 200
    assert client.post("/auth/reset-password", json=payload).status_code == 400


def test_changing_a_password_needs_the_current_one(client, db_session):
    _verified_member(client, db_session)
    headers = {"Authorization": f"Bearer {_login(client).json()['token']}"}

    wrong = client.post(
        "/auth/change-password",
        json={"current_password": "nope-nope-nope", "new_password": "another-good-passphrase"},
        headers=headers,
    )
    right = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "another-good-passphrase"},
        headers=headers,
    )

    assert wrong.status_code == 401 and right.status_code == 200
    assert _login(client, password="another-good-passphrase").status_code == 200


# --- deletion -----------------------------------------------------------------------------


def test_deleting_an_account_removes_the_member_and_their_sessions(client, db_session):
    _verified_member(client, db_session)
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/auth/delete-account", json={"password": PASSWORD}, headers=headers)

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(User).count() == 0
    assert db_session.query(AuthSession).count() == 0
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert _login(client).status_code == 401


def test_deleting_an_account_needs_the_password(client, db_session):
    _verified_member(client, db_session)
    headers = {"Authorization": f"Bearer {_login(client).json()['token']}"}

    response = client.post(
        "/auth/delete-account", json={"password": "wrong-password-1"}, headers=headers
    )

    assert response.status_code == 401
    assert db_session.query(User).count() == 1


def test_an_administrator_cannot_delete_themselves_from_the_member_page(client, db_session):
    _verified_member(client, db_session)
    user = db_session.query(User).one()
    user.role = "admin"
    db_session.commit()
    headers = {"Authorization": f"Bearer {_login(client).json()['token']}"}

    response = client.post("/auth/delete-account", json={"password": PASSWORD}, headers=headers)

    assert response.status_code == 403
    assert db_session.query(User).count() == 1


# --- guards -------------------------------------------------------------------------------


def test_the_admin_area_refuses_members_and_visitors(client, db_session):
    _verified_member(client, db_session)
    headers = {"Authorization": f"Bearer {_login(client).json()['token']}"}

    assert client.get("/admin/overview").status_code == 401
    assert client.get("/admin/overview", headers=headers).status_code == 403
    assert client.get("/admin/users", headers=headers).status_code == 403
    assert client.post("/admin/picks", json={}, headers=headers).status_code == 403
