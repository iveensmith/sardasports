"""Who is calling: the member behind a session token, and the guards built on it.

The website's server forwards the member's session token as `Authorization: Bearer <token>`.
The engine is not reachable from the internet directly (only the website talks to it), and it
still checks the token on every request: a guard that trusted the caller would be a guard that
disappears the day someone exposes the port.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.account import User
from app.services import access, auth_service, premium_service
from app.services.auth_service import AuthError


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def caller_address(request: Request) -> str:
    """A key for rate limits: the visitor's address as the website saw it, else the peer."""
    forwarded = request.headers.get("x-client-ip", "").strip()
    if forwarded:
        return forwarded[:64]
    return request.client.host if request.client else "unknown"


def fail(error: Exception) -> HTTPException:
    """An `AuthError` or `ContentError` as an HTTP response the website can read."""
    code = getattr(error, "code", "error")
    message = getattr(error, "message", str(error))
    status = getattr(error, "status", 400)
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def optional_user(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
) -> User | None:
    return auth_service.user_for_session(db, bearer_token(authorization))


def get_viewer(
    user: User | None = Depends(optional_user), db: Session = Depends(get_db)
) -> access.Viewer:
    """Whether the caller is a premium member. The website's own requests carry no member,
    so they are never premium and always get the hidden version of a locked prediction."""
    return access.Viewer(premium=bool(premium_service.entitlement(db, user)["premium"]))


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise fail(AuthError("not_signed_in", "Please sign in to continue.", 401))
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise fail(AuthError("forbidden", "This area is for administrators.", 403))
    return user
