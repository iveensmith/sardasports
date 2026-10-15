"""The administrator's dashboard API: /admin/*. Every route requires the admin role."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps_auth import admin_user, fail
from app.api.routes_auth import user_view
from app.database.session import get_db
from app.models.account import AuditLog, AuthSession, AuthToken, EmailOutbox, User
from app.models.content import STATUS_PUBLISHED, ManualPick, Post
from app.models.premium import Plan, Subscription
from app.services import content_service, mailer, premium_service
from app.services.content_service import ContentError

router = APIRouter(prefix="/admin", tags=["admin"])


def _wrap(error: ContentError) -> HTTPException:
    return fail(error)


# --- overview -----------------------------------------------------------------------------


@router.get("/overview")
def overview(admin: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    now = datetime.utcnow()  # naive UTC, matching what is stored
    return {
        "users": db.query(func.count(User.id)).scalar(),
        "verified_users": db.query(func.count(User.id))
        .filter(User.email_verified_at.is_not(None))
        .scalar(),
        "premium_members": db.query(func.count(func.distinct(Subscription.user_id)))
        .filter(Subscription.current_period_end > now)
        .scalar(),
        "posts_published": db.query(func.count(Post.id))
        .filter(Post.status == STATUS_PUBLISHED)
        .scalar(),
        "posts_draft": db.query(func.count(Post.id))
        .filter(Post.status != STATUS_PUBLISHED)
        .scalar(),
        "picks": content_service.record(db),
        "mail_configured": mailer.smtp_configured(),
        "mail_unsent": db.query(func.count(EmailOutbox.id))
        .filter(EmailOutbox.sent_at.is_(None))
        .scalar(),
    }


# --- members ------------------------------------------------------------------------------


class GrantIn(BaseModel):
    days: int = Field(ge=1, le=3660)
    note: str = Field(default="", max_length=200)


@router.get("/users")
def users(
    q: str = Query("", max_length=100),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(User)
    if q.strip():
        query = query.filter(User.email.like(f"%{q.strip().lower()}%"))
    rows = query.order_by(User.created_at.desc()).limit(limit).all()
    out = []
    for row in rows:
        view = user_view(row)
        view["entitlement"] = premium_service.entitlement(db, row)
        out.append(view)
    return {"users": out}


def _member(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "No such member."}
        )
    return user


@router.post("/users/{user_id}/grant")
def grant(
    user_id: int, body: GrantIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    user = _member(db, user_id)
    premium_service.grant_manually(db, user=user, days=body.days, actor_id=admin.id, note=body.note)
    db.commit()
    return {"ok": True, "entitlement": premium_service.entitlement(db, user)}


@router.post("/users/{user_id}/revoke")
def revoke(user_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    user = _member(db, user_id)
    ended = premium_service.revoke(db, user=user, actor_id=admin.id)
    db.commit()
    return {"ok": True, "ended": ended}


@router.delete("/users/{user_id}")
def delete_member(
    user_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    user = _member(db, user_id)
    if user.is_admin:
        raise fail(ContentError("admin_protected", "An administrator cannot be deleted here.", 403))
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(synchronize_session=False)
    db.query(AuthToken).filter(AuthToken.user_id == user.id).delete(synchronize_session=False)
    db.query(Subscription).filter(Subscription.user_id == user.id).delete(synchronize_session=False)
    db.add(AuditLog(actor_id=admin.id, action="user.delete", target=f"user:{user.id}"))
    db.delete(user)
    db.commit()
    return {"ok": True}


# --- posts --------------------------------------------------------------------------------


class PostIn(BaseModel):
    title: str = Field(max_length=200)
    excerpt: str = Field(default="", max_length=600)
    body: str = Field(default="", max_length=100_000)
    premium_only: bool = False
    publish: bool = False


@router.get("/posts")
def admin_posts(admin: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    rows = db.query(Post).order_by(Post.created_at.desc()).limit(200).all()
    return {"posts": [content_service.post_view(p) for p in rows]}


@router.get("/posts/{post_id}")
def admin_post(
    post_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    row = db.get(Post, post_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "No such post."}
        )
    return {"post": content_service.post_view(row)}


@router.post("/posts")
def create_post(
    body: PostIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    try:
        row = content_service.save_post(
            db,
            actor=admin,
            post_id=None,
            title=body.title,
            excerpt=body.excerpt,
            body=body.body,
            premium_only=body.premium_only,
            publish=body.publish,
        )
    except ContentError as error:
        raise _wrap(error) from None
    db.commit()
    return {"post": content_service.post_view(row)}


@router.put("/posts/{post_id}")
def update_post(
    post_id: int, body: PostIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    try:
        row = content_service.save_post(
            db,
            actor=admin,
            post_id=post_id,
            title=body.title,
            excerpt=body.excerpt,
            body=body.body,
            premium_only=body.premium_only,
            publish=body.publish,
        )
    except ContentError as error:
        raise _wrap(error) from None
    db.commit()
    return {"post": content_service.post_view(row)}


@router.post("/posts/{post_id}/unpublish")
def unpublish(
    post_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    try:
        row = content_service.unpublish_post(db, actor=admin, post_id=post_id)
    except ContentError as error:
        raise _wrap(error) from None
    db.commit()
    return {"post": content_service.post_view(row)}


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    try:
        content_service.delete_post(db, actor=admin, post_id=post_id)
    except ContentError as error:
        raise _wrap(error) from None
    db.commit()
    return {"ok": True}


# --- picks --------------------------------------------------------------------------------


class PickIn(BaseModel):
    sport: str = Field(default="football", max_length=20)
    competition: str = Field(max_length=120)
    home_team: str = Field(max_length=120)
    away_team: str = Field(max_length=120)
    kickoff: datetime
    market: str = Field(max_length=80)
    selection: str = Field(max_length=120)
    odds: float | None = None
    confidence: int | None = None
    rationale: str = Field(default="", max_length=4000)
    premium_only: bool = False
    publish: bool = False


class SettleIn(BaseModel):
    result: str = Field(max_length=10)
    void_reason: str | None = Field(default=None, max_length=200)


@router.get("/picks")
def admin_picks(admin: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    rows = db.query(ManualPick).order_by(ManualPick.kickoff.desc()).limit(300).all()
    return {
        "picks": [content_service.pick_view(p, viewer_has_premium=True) for p in rows],
        "record": content_service.record(db),
    }


@router.post("/picks")
def create_pick(
    body: PickIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    try:
        row = content_service.create_pick(db, actor=admin, **body.model_dump())
    except ContentError as error:
        raise _wrap(error) from None
    db.commit()
    return {"pick": content_service.pick_view(row, viewer_has_premium=True)}


@router.post("/picks/{pick_id}/publish")
def publish_pick(
    pick_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    try:
        row = content_service.publish_pick(db, actor=admin, pick_id=pick_id)
    except ContentError as error:
        raise _wrap(error) from None
    db.commit()
    return {"pick": content_service.pick_view(row, viewer_has_premium=True)}


@router.post("/picks/{pick_id}/settle")
def settle_pick(
    pick_id: int, body: SettleIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    try:
        row = content_service.settle_pick(
            db, actor=admin, pick_id=pick_id, result=body.result, void_reason=body.void_reason
        )
    except ContentError as error:
        raise _wrap(error) from None
    db.commit()
    return {"pick": content_service.pick_view(row, viewer_has_premium=True)}


@router.delete("/picks/{pick_id}")
def delete_pick(
    pick_id: int, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    try:
        content_service.delete_pick(db, actor=admin, pick_id=pick_id)
    except ContentError as error:
        raise _wrap(error) from None
    db.commit()
    return {"ok": True}


# --- plans, mail, audit -------------------------------------------------------------------


class PlanIn(BaseModel):
    code: str = Field(max_length=40)
    name: str = Field(max_length=80)
    description: str = Field(default="", max_length=300)
    price_minor: int = Field(ge=1)
    currency: str = Field(min_length=3, max_length=3)
    interval: str = Field(max_length=10)
    active: bool = False


@router.get("/plans")
def admin_plans(admin: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    rows = db.query(Plan).order_by(Plan.price_minor.asc()).all()
    return {"plans": [premium_service.plan_view(p) for p in rows]}


@router.post("/plans")
def save_plan(
    body: PlanIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict:
    try:
        plan = premium_service.save_plan(db, **body.model_dump())
    except ValueError as error:
        raise HTTPException(
            status_code=400, detail={"code": "bad_plan", "message": str(error)}
        ) from None
    db.add(
        AuditLog(
            actor_id=admin.id,
            action="plan.save",
            target=f"plan:{plan.code}",
            detail=f"{plan.price_minor} {plan.currency}/{plan.interval} active={plan.active}",
        )
    )
    db.commit()
    return {"plan": premium_service.plan_view(plan)}


@router.get("/outbox")
def outbox(
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.query(EmailOutbox).order_by(EmailOutbox.id.desc()).limit(limit).all()
    return {
        "mail_configured": mailer.smtp_configured(),
        "messages": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "to": r.to_address,
                "subject": r.subject,
                "body": r.body_text,
                "kind": r.kind,
                "sent": r.sent_at is not None,
                "attempts": r.attempts,
                "error": r.last_error,
            }
            for r in rows
        ],
    }


@router.get("/audit")
def audit(
    limit: int = Query(100, ge=1, le=500),
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return {
        "entries": [
            {
                "id": r.id,
                "at": r.created_at.isoformat() if r.created_at else None,
                "actor_id": r.actor_id,
                "action": r.action,
                "target": r.target,
                "detail": r.detail,
            }
            for r in rows
        ]
    }
