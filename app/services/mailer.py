"""Outgoing e-mail: write to the outbox first, then send if a mail server is configured.

Writing first means a mail-server outage never loses a verification link, and until SMTP is set up
the administrator can read every message in the outbox and pass a link on by hand. Sending happens
in a background thread so a slow mail server never holds up a sign-up request.
"""

from __future__ import annotations

import logging
import smtplib
import threading
from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.account import EmailOutbox
from app.utils.config import get_settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


def smtp_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_from)


def queue_email(db: Session, to: str, subject: str, body: str, kind: str) -> EmailOutbox:
    """Store a message for sending. Does not commit: it travels with the caller's transaction,
    so a message about a change is only ever sent if the change itself was saved."""
    row = EmailOutbox(to_address=to, subject=subject[:200], body_text=body, kind=kind)
    db.add(row)
    db.flush()
    return row


def _send_one(row: EmailOutbox) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = row.to_address
    message["Subject"] = row.subject
    message.set_content(row.body_text)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)


def deliver_pending(limit: int = 20) -> int:
    """Send unsent messages (own session). Returns how many went out."""
    if not smtp_configured():
        return 0
    sent = 0
    session = SessionLocal()
    try:
        rows = (
            session.query(EmailOutbox)
            .filter(EmailOutbox.sent_at.is_(None), EmailOutbox.attempts < MAX_ATTEMPTS)
            .order_by(EmailOutbox.id.asc())
            .limit(limit)
            .all()
        )
        for row in rows:
            row.attempts += 1
            try:
                _send_one(row)
                row.sent_at = datetime.now(UTC).replace(tzinfo=None)
                row.last_error = None
                sent += 1
            except Exception as exc:  # noqa: BLE001 - one bad message must not stop the rest
                row.last_error = str(exc)[:300]
                logger.warning("mail to %s failed: %s", row.to_address, exc)
            session.commit()
    finally:
        session.close()
    return sent


def deliver_in_background() -> None:
    """Fire and forget: called after the request's transaction has committed."""
    if not smtp_configured():
        return
    threading.Thread(target=deliver_pending, daemon=True, name="mail-delivery").start()
