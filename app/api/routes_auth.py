"""Accounts: /auth/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps_auth import (
    bearer_token,
    caller_address,
    current_user,
    fail,
)
from app.database.session import get_db
from app.models.account import User
from app.services import auth_service, mailer, premium_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str | None = Field(default=None, max_length=300)
    password: str | None = Field(default=None, max_length=300)
    over_18: bool = False
    accept_terms: bool = False
    display_name: str | None = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    email: str | None = Field(default=None, max_length=300)
    password: str | None = Field(default=None, max_length=300)


class TokenIn(BaseModel):
    token: str | None = Field(default=None, max_length=200)


class EmailIn(BaseModel):
    email: str | None = Field(default=None, max_length=300)


class ResetIn(BaseModel):
    token: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=300)


class ChangePasswordIn(BaseModel):
    current_password: str | None = Field(default=None, max_length=300)
    new_password: str | None = Field(default=None, max_length=300)


class DeleteIn(BaseModel):
    password: str | None = Field(default=None, max_length=300)


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    marketing_opt_in: bool | None = None


def user_view(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "email_verified": user.email_verified,
        "over_18_confirmed": user.over_18_confirmed_at is not None,
        "marketing_opt_in": user.marketing_opt_in,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.post("/register")
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)) -> dict:
    try:
        auth_service.register(
            db,
            email=body.email,
            password=body.password,
            over_18=body.over_18,
            accept_terms=body.accept_terms,
            display_name=body.display_name,
            caller=caller_address(request),
        )
    except AuthError as error:
        raise fail(error) from None
    # The same answer whether or not the address was already registered.
    return {
        "ok": True,
        "message": "Check your inbox: we sent a link to confirm your e-mail address.",
        "mail_configured": mailer.smtp_configured(),
    }


@router.post("/verify-email")
def verify_email(body: TokenIn, db: Session = Depends(get_db)) -> dict:
    try:
        user = auth_service.verify_email(db, body.token)
    except AuthError as error:
        raise fail(error) from None
    return {"ok": True, "email": user.email}


@router.post("/resend-verification")
def resend_verification(body: EmailIn, request: Request, db: Session = Depends(get_db)) -> dict:
    try:
        auth_service.resend_verification(db, body.email, caller=caller_address(request))
    except AuthError as error:
        raise fail(error) from None
    return {"ok": True, "message": "If that address has an account, a new link is on its way."}


@router.post("/login")
def login(
    body: LoginIn,
    request: Request,
    db: Session = Depends(get_db),
    user_agent: str | None = Header(default=None),
) -> dict:
    try:
        user, token = auth_service.login(
            db,
            email=body.email,
            password=body.password,
            user_agent=user_agent,
            caller=caller_address(request),
        )
    except AuthError as error:
        raise fail(error) from None
    return {
        "token": token,
        "user": user_view(user),
        "entitlement": premium_service.entitlement(db, user),
    }


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    auth_service.logout(db, bearer_token(authorization))
    return {"ok": True}


@router.post("/logout-all")
def logout_all(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    auth_service.logout_everywhere(db, user)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return {"user": user_view(user), "entitlement": premium_service.entitlement(db, user)}


@router.patch("/profile")
def update_profile(
    body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    if body.display_name is not None:
        user.display_name = body.display_name.strip()[:80] or None
    if body.marketing_opt_in is not None:
        user.marketing_opt_in = bool(body.marketing_opt_in)
    db.commit()
    return {"user": user_view(user)}


@router.post("/forgot-password")
def forgot_password(body: EmailIn, request: Request, db: Session = Depends(get_db)) -> dict:
    try:
        auth_service.request_password_reset(db, body.email, caller=caller_address(request))
    except AuthError as error:
        raise fail(error) from None
    return {
        "ok": True,
        "message": "If that address has an account, a reset link is on its way.",
    }


@router.post("/reset-password")
def reset_password(body: ResetIn, db: Session = Depends(get_db)) -> dict:
    try:
        auth_service.reset_password(db, body.token, body.password)
    except AuthError as error:
        raise fail(error) from None
    return {"ok": True}


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    try:
        auth_service.change_password(db, user, body.current_password, body.new_password)
    except AuthError as error:
        raise fail(error) from None
    return {"ok": True}


@router.post("/delete-account")
def delete_account(
    body: DeleteIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    if user.is_admin:
        # The last administrator deleting themselves would lock the dashboard for good.
        raise fail(
            AuthError(
                "admin_protected",
                "An administrator account cannot be deleted from here.",
                403,
            )
        )
    try:
        auth_service.delete_account(db, user, body.password)
    except AuthError as error:
        raise fail(error) from None
    return {"ok": True}
