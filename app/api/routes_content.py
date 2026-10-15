"""Public content: the blog and the editor's picks.

Anyone can read what is public. A signed-in member with an active premium plan also sees the body
of premium posts and the details of premium picks before kick-off; everyone else sees a locked
view with the headline.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps_auth import optional_user
from app.database.session import get_db
from app.models.account import User
from app.models.content import STATUS_PUBLISHED, ManualPick, Post
from app.services import content_service, media_service, premium_service

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/categories")
def categories() -> dict:
    return {"categories": list(content_service.CATEGORIES)}


@router.get("/media/{name}")
def media(name: str) -> FileResponse:
    """An uploaded blog image. Immutable: a name is never reused for different bytes."""
    path = media_service.path_for(name)
    if path is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "No such image."}
        )
    return FileResponse(
        path,
        media_type=media_service.CONTENT_TYPES.get(
            path.suffix.lstrip("."), "application/octet-stream"
        ),
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/posts")
def posts(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category: str | None = Query(None, max_length=60),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(Post).filter(Post.status == STATUS_PUBLISHED)
    if category:
        query = query.filter(Post.category == category)
    total = query.count()
    rows = query.order_by(Post.published_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "posts": [content_service.post_view(p, include_body=False) for p in rows],
    }


@router.get("/posts/{slug}")
def post(
    slug: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)
) -> dict:
    row = db.query(Post).filter(Post.slug == slug, Post.status == STATUS_PUBLISHED).first()
    if row is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "No such post."}
        )
    locked = row.premium_only and not premium_service.has_premium(db, user)
    return {"post": content_service.post_view(row, locked=locked)}


@router.get("/picks")
def picks(
    scope: str = Query("upcoming", pattern="^(upcoming|recent)$"),
    limit: int = Query(30, ge=1, le=100),
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> dict:
    now = datetime.now(UTC).replace(tzinfo=None)
    query = db.query(ManualPick).filter(ManualPick.status == STATUS_PUBLISHED)
    if scope == "upcoming":
        # A match that kicked off up to three hours ago is still "today's" for a reader.
        query = query.filter(ManualPick.kickoff >= now - timedelta(hours=3)).order_by(
            ManualPick.kickoff.asc()
        )
    else:
        query = query.filter(ManualPick.kickoff < now - timedelta(hours=3)).order_by(
            ManualPick.kickoff.desc()
        )
    member = premium_service.has_premium(db, user)
    return {
        "scope": scope,
        "premium": member,
        "picks": [
            content_service.pick_view(p, viewer_has_premium=member, now=now)
            for p in query.limit(limit).all()
        ],
    }


@router.get("/picks/record")
def picks_record(db: Session = Depends(get_db)) -> dict:
    return content_service.record(db)
