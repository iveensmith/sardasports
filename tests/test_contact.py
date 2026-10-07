"""The Contact form.

It is a public endpoint that writes to the database, so what is pinned here is the
behaviour that keeps it safe and honest: bad input is refused with a reason, a bot
is dropped without being told, abuse is rate limited, and nothing about the sender
beyond what they typed is stored.
"""

from __future__ import annotations

import pytest

import app.services.contact_service as contact
from app.models import ContactMessage

VALID = {
    "topic": "error",
    "name": "Sam",
    "email": "sam@example.com",
    "message": "The result for yesterday's first match looks wrong on the record.",
}


@pytest.fixture(autouse=True)
def _fresh_limits():
    contact.reset_limits()
    yield
    contact.reset_limits()


def _submit(db_session, **overrides):
    payload = {**VALID, "honeypot": None, "client_key": "visitor-1", **overrides}
    return contact.submit(db_session, **payload)


# --- validation -----------------------------------------------------------------------------------


def test_a_valid_message_is_stored_as_typed(db_session):
    assert _submit(db_session) is True

    stored = db_session.query(ContactMessage).one()
    assert (stored.topic, stored.name, stored.email) == ("error", "Sam", "sam@example.com")
    assert stored.message.startswith("The result for yesterday")
    assert stored.handled is False


def test_the_name_is_optional(db_session):
    _submit(db_session, name=None)
    _submit(db_session, name="   ", client_key="visitor-2")

    assert [m.name for m in db_session.query(ContactMessage).all()] == [None, None]


@pytest.mark.parametrize(
    "field, value",
    [
        ("topic", "spam"),
        ("topic", ""),
        ("email", ""),
        ("email", "not-an-email"),
        ("email", "a@b"),
        ("message", "short"),
        ("message", "x" * 5001),
        ("name", "n" * 121),
    ],
)
def test_bad_input_is_refused_with_a_reason_for_that_field(db_session, field, value):
    with pytest.raises(contact.ContactError) as raised:
        _submit(db_session, **{field: value})

    assert field in raised.value.errors
    assert raised.value.errors[field]  # a sentence, not an empty string
    assert db_session.query(ContactMessage).count() == 0


def test_every_problem_is_reported_at_once_not_one_per_attempt(db_session):
    with pytest.raises(contact.ContactError) as raised:
        _submit(db_session, topic="x", email="nope", message="hi")

    assert set(raised.value.errors) == {"topic", "email", "message"}


def test_surrounding_whitespace_is_trimmed(db_session):
    _submit(db_session, email="  sam@example.com  ", message="  " + VALID["message"] + "  ")

    stored = db_session.query(ContactMessage).one()
    assert stored.email == "sam@example.com"
    assert stored.message == VALID["message"]


# --- abuse ----------------------------------------------------------------------------------------


def test_a_filled_honeypot_is_dropped_without_a_trace_and_without_an_error(db_session):
    result = _submit(db_session, honeypot="http://spam.example")

    assert result is False  # not stored...
    assert db_session.query(ContactMessage).count() == 0  # ...and no exception to tip the bot off


def test_a_visitor_is_limited_to_a_few_messages_an_hour(db_session):
    for _ in range(contact.PER_CLIENT_PER_HOUR):
        _submit(db_session)

    with pytest.raises(contact.RateLimited):
        _submit(db_session)
    assert db_session.query(ContactMessage).count() == contact.PER_CLIENT_PER_HOUR


def test_one_visitors_limit_does_not_block_another(db_session):
    for _ in range(contact.PER_CLIENT_PER_HOUR):
        _submit(db_session, client_key="busy")

    assert _submit(db_session, client_key="someone-else") is True


def test_the_whole_site_is_capped_too(db_session, monkeypatch):
    monkeypatch.setattr(contact, "SITE_WIDE_PER_HOUR", 2)
    _submit(db_session, client_key="a")
    _submit(db_session, client_key="b")

    with pytest.raises(contact.RateLimited):
        _submit(db_session, client_key="c")


def test_a_refused_message_does_not_use_up_the_visitors_allowance(db_session):
    for _ in range(contact.PER_CLIENT_PER_HOUR + 2):
        with pytest.raises(contact.ContactError):
            _submit(db_session, message="short")

    assert _submit(db_session) is True


# --- privacy --------------------------------------------------------------------------------------


def test_only_what_the_sender_typed_is_stored():
    """No address, no browser string: the policy says so, and the schema makes it so."""
    columns = {c.name for c in ContactMessage.__table__.columns}

    assert columns == {"id", "created_at", "topic", "name", "email", "message", "handled"}


# --- the endpoint ---------------------------------------------------------------------------------


def test_the_endpoint_accepts_a_good_message(client, db_session):
    response = client.post("/contact", json={**VALID, "website": ""})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert db_session.query(ContactMessage).count() == 1


def test_the_endpoint_says_ok_to_a_bot_and_stores_nothing(client, db_session):
    response = client.post("/contact", json={**VALID, "website": "http://spam.example"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert db_session.query(ContactMessage).count() == 0


def test_the_endpoint_returns_field_errors_as_422(client):
    response = client.post("/contact", json={**VALID, "email": "nope"})

    assert response.status_code == 422
    assert "email" in response.json()["detail"]["errors"]


def test_the_endpoint_rate_limits_with_a_429(client):
    for _ in range(contact.PER_CLIENT_PER_HOUR):
        assert (
            client.post("/contact", json=VALID, headers={"X-Contact-Client": "v"}).status_code
            == 200
        )

    blocked = client.post("/contact", json=VALID, headers={"X-Contact-Client": "v"})

    assert blocked.status_code == 429
    assert "try again" in blocked.json()["detail"].lower()


def test_the_visitor_token_keeps_visitors_apart(client):
    for _ in range(contact.PER_CLIENT_PER_HOUR):
        client.post("/contact", json=VALID, headers={"X-Contact-Client": "one"})

    other = client.post("/contact", json=VALID, headers={"X-Contact-Client": "two"})

    assert other.status_code == 200


def test_the_topics_endpoint_matches_what_the_service_accepts(client):
    topics = client.get("/contact/topics").json()["topics"]

    assert {t["value"] for t in topics} == set(contact.TOPICS)


def test_a_visitors_token_is_discarded_once_its_hour_is_up(db_session, monkeypatch):
    """The privacy policy says these tokens are discarded when they expire."""
    _submit(db_session, client_key="gone-soon")
    assert "gone-soon" in contact._by_client

    monkeypatch.setattr(contact, "_WINDOW_SECONDS", -1)
    _submit(db_session, client_key="someone-else")

    assert "gone-soon" not in contact._by_client


def test_an_empty_or_null_form_gets_our_own_field_messages_not_a_schema_error(client):
    """What a browser sends when nothing was chosen or typed."""
    for body in ({}, {"topic": None, "email": None, "message": None, "name": None}):
        response = client.post("/contact", json=body)

        assert response.status_code == 422
        errors = response.json()["detail"]["errors"]
        assert set(errors) == {"topic", "email", "message"}
        assert all(isinstance(text, str) and text for text in errors.values())
