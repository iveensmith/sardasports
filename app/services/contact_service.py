"""The Contact form: validation, abuse protection and storage.

A public form is an invitation to bots, so three cheap defences sit in front of
the database:

* a hidden field a person never sees and a bot fills in; a message that has it is
  quietly dropped, with the same success response, so a bot learns nothing;
* a per-visitor limit and a site-wide limit on how many messages are accepted per
  hour;
* hard limits on every field's length.

The rate limit is kept in memory and keyed on an opaque token the website derives
from the visitor (a daily-changing hash of their connection), never on an address
stored here, and a token is discarded once its hour is up. Nothing identifying the sender
beyond what they typed is ever written to the database, which is what lets the
privacy policy describe the form in one sentence.
"""

from __future__ import annotations

import re
import threading
from collections import deque
from time import monotonic

from sqlalchemy.orm import Session

from app.models.contact_message import ContactMessage

TOPICS: dict[str, str] = {
    "general": "General question",
    "error": "A wrong pick, result or number",
    "data": "Data, copyright or attribution",
    "press": "Press or partnership",
    "privacy": "A privacy request",
}

NAME_MAX = 120
EMAIL_MAX = 254
MESSAGE_MIN = 10
MESSAGE_MAX = 5000

PER_CLIENT_PER_HOUR = 3
SITE_WIDE_PER_HOUR = 60
_WINDOW_SECONDS = 3600

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

_lock = threading.Lock()
_by_client: dict[str, deque[float]] = {}
_site: deque[float] = deque()
_table_ready = False


class ContactError(ValueError):
    """The submission is not acceptable. `errors` maps a field to what is wrong."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


class RateLimited(Exception):
    """Too many messages from this visitor, or from the site as a whole."""


def reset_limits() -> None:
    """For tests."""
    global _table_ready
    with _lock:
        _by_client.clear()
        _site.clear()
    _table_ready = False


def ensure_table(session: Session) -> None:
    """Create the table on first use, so a database that has not run the migration
    still takes messages. The migration is written to tolerate the table existing."""
    global _table_ready
    if _table_ready:
        return
    ContactMessage.__table__.create(bind=session.get_bind(), checkfirst=True)
    _table_ready = True


def validate(*, topic: str, name: str | None, email: str, message: str) -> dict:
    errors: dict[str, str] = {}

    topic = (topic or "").strip()
    if topic not in TOPICS:
        errors["topic"] = "Choose what your message is about."

    name = (name or "").strip() or None
    if name and len(name) > NAME_MAX:
        errors["name"] = f"Keep your name under {NAME_MAX} characters."

    email = (email or "").strip()
    if not email:
        errors["email"] = "Enter an email address so a reply can reach you."
    elif len(email) > EMAIL_MAX or not _EMAIL.match(email):
        errors["email"] = "That does not look like a valid email address."

    message = (message or "").strip()
    if len(message) < MESSAGE_MIN:
        errors["message"] = "Tell us a little more: a sentence or two is enough."
    elif len(message) > MESSAGE_MAX:
        errors["message"] = f"Keep your message under {MESSAGE_MAX:,} characters."

    if errors:
        raise ContactError(errors)
    return {"topic": topic, "name": name, "email": email, "message": message}


def _allow(client_key: str) -> bool:
    now = monotonic()
    with _lock:
        # Forget anything older than the window, including whole visitors: the
        # privacy policy says these tokens are discarded when they expire, so they
        # really are, not merely emptied.
        for key in [
            k for k, hits in _by_client.items() if not hits or now - hits[-1] > _WINDOW_SECONDS
        ]:
            del _by_client[key]
        while _site and now - _site[0] > _WINDOW_SECONDS:
            _site.popleft()
        client = _by_client.setdefault(client_key, deque())
        while client and now - client[0] > _WINDOW_SECONDS:
            client.popleft()
        if len(client) >= PER_CLIENT_PER_HOUR or len(_site) >= SITE_WIDE_PER_HOUR:
            return False
        client.append(now)
        _site.append(now)
        return True


def submit(
    session: Session,
    *,
    topic: str,
    name: str | None,
    email: str,
    message: str,
    honeypot: str | None,
    client_key: str,
) -> bool:
    """Validate, rate-limit and store one message. Returns True when it was kept.

    A filled honeypot returns False without raising: the caller reports success
    either way, so a bot cannot tell it was caught.
    """
    clean = validate(topic=topic, name=name, email=email, message=message)
    if honeypot and honeypot.strip():
        return False
    if not _allow(client_key):
        raise RateLimited
    ensure_table(session)
    session.add(ContactMessage(**clean))
    session.commit()
    return True
