"""Accounts: sign-up, e-mail verification, sign-in, sessions, password reset, deletion.

Security decisions, each deliberate:

* **Passwords** are hashed with scrypt (standard library, memory-hard) with a random salt per
  password, and compared in constant time. They are never logged and never returned.
* **Sessions and e-mail tokens** are random 256-bit values. Only their SHA-256 is stored, so a
  leaked database copy contains no usable credential. Tokens are single-use and expire.
* **No account enumeration.** Registering an address that already has an account, and asking for a
  reset for an unknown address, both answer exactly as the normal case does; the difference is
  only in the e-mail the real owner of the address receives.
* **Rate limits** on sign-in (per address and per caller), sign-up and reset requests, in memory
  (one process, one box). A failed sign-in costs the same time whether or not the account exists.
* **Age and terms** are recorded with a date: a member cannot exist without confirming 18 or over.
* **Deleting an account** needs the password, removes the member's sessions, tokens and
  subscriptions, and keeps nothing that identifies them.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.account import (
    ROLE_MEMBER,
    TOKEN_RESET_PASSWORD,
    TOKEN_VERIFY_EMAIL,
    AuditLog,
    AuthSession,
    AuthToken,
    User,
)
from app.models.content import ManualPick, Post
from app.models.premium import Subscription
from app.services import mailer
from app.utils.config import get_settings

# --- scrypt parameters (n, r, p). Memory used is 128 * n * r bytes: 16 MiB. -----------------
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_KEYLEN = 32

MIN_PASSWORD = 10
MAX_PASSWORD = 128
TERMS_VERSION = "2026-10"

_EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")

# The commonest passwords and password shapes. A short list on purpose: the aim is to refuse the
# ones attackers try first, not to lecture.
_COMMON = frozenset(
    {
        "password",
        "password1",
        "password123",
        "1234567890",
        "12345678910",
        "qwertyuiop",
        "iloveyou123",
        "letmein123",
        "welcome123",
        "football123",
        "sardasports",
        "admin12345",
    }
)


class AuthError(Exception):
    """A refusal with a stable `code` the website can show a message for."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# --- passwords ----------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_KEYLEN,
        maxmem=64 * 1024 * 1024,
    )
    salt_b64 = base64.b64encode(salt).decode()
    digest_b64 = base64.b64encode(digest).decode()
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt_b64}${digest_b64}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=64 * 1024 * 1024,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


# A hash to check a password against when the account does not exist, so that "no such account"
# takes as long as "wrong password" and the difference cannot be timed.
_DUMMY_HASH = hash_password("not-a-real-password-" + secrets.token_hex(8))


def validate_email(raw: str | None) -> str:
    email = (raw or "").strip().lower()
    if not email or len(email) > 254 or not _EMAIL_RE.match(email):
        raise AuthError("invalid_email", "Enter a valid e-mail address.")
    return email


def validate_password(password: str | None, email: str = "") -> str:
    value = password or ""
    if len(value) < MIN_PASSWORD:
        raise AuthError("weak_password", f"Use at least {MIN_PASSWORD} characters.")
    if len(value) > MAX_PASSWORD:
        raise AuthError("weak_password", f"Use no more than {MAX_PASSWORD} characters.")
    lowered = value.lower()
    if lowered in _COMMON or (email and lowered == email.split("@")[0]):
        raise AuthError("weak_password", "That password is too easy to guess. Choose another.")
    if len(set(value)) < 4:
        raise AuthError("weak_password", "That password is too repetitive. Choose another.")
    return value


# --- rate limiting (in memory; one process) -----------------------------------------------

_hits: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    """For tests."""
    _hits.clear()


def _limit(key: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    hits = _hits[key]
    while hits and now - hits[0] > window_seconds:
        hits.popleft()
    if len(hits) >= limit:
        raise AuthError(
            "rate_limited", "Too many attempts. Please wait a few minutes and try again.", 429
        )
    hits.append(now)


# --- tokens -------------------------------------------------------------------------------


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _issue_token(db: Session, user: User, kind: str, hours: int) -> str:
    """Create a single-use token, retiring any earlier unused one of the same kind."""
    db.query(AuthToken).filter(
        AuthToken.user_id == user.id, AuthToken.kind == kind, AuthToken.used_at.is_(None)
    ).delete(synchronize_session=False)
    token = _new_token()
    db.add(
        AuthToken(
            user_id=user.id,
            kind=kind,
            token_hash=_hash_token(token),
            expires_at=_now() + timedelta(hours=hours),
        )
    )
    return token


def _consume_token(db: Session, token: str, kind: str) -> User:
    row = (
        db.query(AuthToken)
        .filter(AuthToken.token_hash == _hash_token(token or ""), AuthToken.kind == kind)
        .first()
    )
    if row is None or row.used_at is not None or row.expires_at < _now():
        raise AuthError("token_invalid", "This link is invalid or has expired. Request a new one.")
    user = db.get(User, row.user_id)
    if user is None:
        raise AuthError("token_invalid", "This link is invalid or has expired.")
    row.used_at = _now()
    return user


def _link(path: str, token: str) -> str:
    base = get_settings().public_site_url.rstrip("/")
    return f"{base}{path}?token={token}" if base else f"{path}?token={token}"


# --- e-mails ------------------------------------------------------------------------------


def _mail_verify(db: Session, user: User, token: str) -> None:
    link = _link("/verify-email", token)
    mailer.queue_email(
        db,
        user.email,
        "Confirm your SARDASPORTS e-mail address",
        "Welcome to SARDASPORTS.\n\n"
        f"Confirm your e-mail address to finish creating your account:\n{link}\n\n"
        f"The link works for {get_settings().verify_token_hours} hours. "
        "If you did not create an account, you can ignore this message.\n",
        "verify_email",
    )


def _mail_reset(db: Session, user: User, token: str) -> None:
    link = _link("/reset-password", token)
    mailer.queue_email(
        db,
        user.email,
        "Reset your SARDASPORTS password",
        "Someone asked to reset the password for this account.\n\n"
        f"Choose a new password here:\n{link}\n\n"
        f"The link works for {get_settings().reset_token_hours} hour and can be used once. "
        "If this was not you, ignore this message: your password has not changed.\n",
        "reset_password",
    )


def _mail_already_registered(db: Session, user: User) -> None:
    mailer.queue_email(
        db,
        user.email,
        "You already have a SARDASPORTS account",
        "Someone tried to create a SARDASPORTS account with this address, but you already "
        "have one.\n\nIf it was you, simply sign in. If you forgot your password you can reset "
        "it from the sign-in page. If it was not you, no action is needed.\n",
        "already_registered",
    )


# --- sign-up and verification -------------------------------------------------------------


def register(
    db: Session,
    *,
    email: str | None,
    password: str | None,
    over_18: bool,
    accept_terms: bool,
    display_name: str | None = None,
    caller: str = "unknown",
) -> None:
    """Create an unverified account and e-mail a confirmation link.

    Returns nothing, whether the address was new or not (see "no account enumeration").
    """
    _limit(f"register:ip:{caller}", 10, 3600)
    address = validate_email(email)
    if not over_18:
        raise AuthError(
            "age_required", "You must confirm that you are 18 or over to create an account."
        )
    if not accept_terms:
        raise AuthError("terms_required", "Please accept the Terms and the Privacy policy.")
    secret = validate_password(password, address)
    _limit(f"register:email:{address}", 3, 3600)

    existing = db.query(User).filter(User.email == address).first()
    if existing is not None:
        _mail_already_registered(db, existing)
        db.commit()
        mailer.deliver_in_background()
        return

    now = _now()
    user = User(
        email=address,
        password_hash=hash_password(secret),
        role=ROLE_MEMBER,
        display_name=(display_name or "").strip()[:80] or None,
        over_18_confirmed_at=now,
        terms_accepted_version=TERMS_VERSION,
    )
    db.add(user)
    db.flush()
    token = _issue_token(db, user, TOKEN_VERIFY_EMAIL, get_settings().verify_token_hours)
    _mail_verify(db, user, token)
    db.commit()
    mailer.deliver_in_background()


def verify_email(db: Session, token: str | None) -> User:
    user = _consume_token(db, token or "", TOKEN_VERIFY_EMAIL)
    if user.email_verified_at is None:
        user.email_verified_at = _now()
    db.commit()
    return user


def resend_verification(db: Session, email: str | None, caller: str = "unknown") -> None:
    """Send a fresh link if the address has an unverified account. Always answers the same."""
    _limit(f"resend:ip:{caller}", 10, 3600)
    address = (email or "").strip().lower()
    if not address:
        return
    _limit(f"resend:email:{address}", 3, 3600)
    user = db.query(User).filter(User.email == address).first()
    if user is not None and user.email_verified_at is None:
        token = _issue_token(db, user, TOKEN_VERIFY_EMAIL, get_settings().verify_token_hours)
        _mail_verify(db, user, token)
        db.commit()
        mailer.deliver_in_background()


# --- sign-in and sessions -----------------------------------------------------------------


def login(
    db: Session,
    *,
    email: str | None,
    password: str | None,
    user_agent: str | None = None,
    caller: str = "unknown",
) -> tuple[User, str]:
    """Check the credentials and open a session. Returns (user, session_token)."""
    address = (email or "").strip().lower()
    _limit(f"login:ip:{caller}", 40, 900)
    _limit(f"login:email:{address}", 8, 900)

    user = db.query(User).filter(User.email == address).first()
    # Always spend one scrypt, so an unknown address takes as long as a known one.
    stored = user.password_hash if user is not None else _DUMMY_HASH
    ok = verify_password(password or "", stored)
    if user is None or not ok:
        raise AuthError("invalid_credentials", "E-mail or password is not right.", 401)
    if user.email_verified_at is None:
        raise AuthError(
            "not_verified",
            "Confirm your e-mail address first. We sent you a link when you signed up.",
            403,
        )

    token = _new_token()
    settings = get_settings()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=_hash_token(token),
            expires_at=_now() + timedelta(days=settings.session_days),
            last_seen_at=_now(),
            user_agent=(user_agent or "")[:160] or None,
        )
    )
    user.last_login_at = _now()
    # Housekeeping: expired sessions and spent tokens do not need to live on.
    db.query(AuthSession).filter(AuthSession.expires_at < _now()).delete(synchronize_session=False)
    db.commit()
    return user, token


def user_for_session(db: Session, token: str | None) -> User | None:
    """The member behind a session token, or None. Slides the expiry forward when it is used."""
    if not token:
        return None
    row = db.query(AuthSession).filter(AuthSession.token_hash == _hash_token(token)).first()
    if row is None or row.expires_at < _now():
        return None
    user = db.get(User, row.user_id)
    if user is None:
        return None
    now = _now()
    # Touch at most once an hour: a write on every request would be wasteful.
    if row.last_seen_at is None or now - row.last_seen_at > timedelta(hours=1):
        row.last_seen_at = now
        row.expires_at = now + timedelta(days=get_settings().session_days)
        db.commit()
    return user


def logout(db: Session, token: str | None) -> None:
    if token:
        db.query(AuthSession).filter(AuthSession.token_hash == _hash_token(token)).delete(
            synchronize_session=False
        )
        db.commit()


def logout_everywhere(db: Session, user: User) -> None:
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(synchronize_session=False)
    db.commit()


# --- password reset and change ------------------------------------------------------------


def request_password_reset(db: Session, email: str | None, caller: str = "unknown") -> None:
    """E-mail a reset link if the address has an account. Always answers the same."""
    _limit(f"reset:ip:{caller}", 10, 3600)
    address = (email or "").strip().lower()
    if not address:
        return
    _limit(f"reset:email:{address}", 3, 3600)
    user = db.query(User).filter(User.email == address).first()
    if user is not None:
        token = _issue_token(db, user, TOKEN_RESET_PASSWORD, get_settings().reset_token_hours)
        _mail_reset(db, user, token)
        db.commit()
        mailer.deliver_in_background()


def reset_password(db: Session, token: str | None, new_password: str | None) -> None:
    user = _consume_token(db, token or "", TOKEN_RESET_PASSWORD)
    secret = validate_password(new_password, user.email)
    user.password_hash = hash_password(secret)
    # A reset also proves the member controls the address.
    if user.email_verified_at is None:
        user.email_verified_at = _now()
    # Whoever had the old password must be signed out everywhere.
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(synchronize_session=False)
    db.commit()


def change_password(db: Session, user: User, current: str | None, new: str | None) -> None:
    if not verify_password(current or "", user.password_hash):
        raise AuthError("invalid_credentials", "Your current password is not right.", 401)
    user.password_hash = hash_password(validate_password(new, user.email))
    db.commit()


# --- deletion -----------------------------------------------------------------------------


def delete_account(db: Session, user: User, password: str | None) -> None:
    """Remove the member and everything that identifies them. Needs the password."""
    if not verify_password(password or "", user.password_hash):
        raise AuthError("invalid_credentials", "Your password is not right.", 401)
    user_id = user.id
    address = user.email
    db.query(AuthSession).filter(AuthSession.user_id == user_id).delete(synchronize_session=False)
    db.query(AuthToken).filter(AuthToken.user_id == user_id).delete(synchronize_session=False)
    db.query(Subscription).filter(Subscription.user_id == user_id).delete(synchronize_session=False)
    # Content the member wrote stays (an administrator's published picks are a record), but no
    # longer points at them.
    db.query(Post).filter(Post.author_id == user_id).update(
        {Post.author_id: None}, synchronize_session=False
    )
    db.query(ManualPick).filter(ManualPick.created_by == user_id).update(
        {ManualPick.created_by: None}, synchronize_session=False
    )
    db.add(AuditLog(actor_id=None, action="account.deleted", target=f"user:{user_id}"))
    mailer.queue_email(
        db,
        address,
        "Your SARDASPORTS account has been deleted",
        "As you asked, your SARDASPORTS account and the data attached to it have been "
        "deleted.\n\nIf you did not ask for this, please contact us straight away.\n",
        "account_deleted",
    )
    db.delete(user)
    db.commit()
    mailer.deliver_in_background()
