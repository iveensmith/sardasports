"""The administrator's content: blog posts and hand-written picks.

Two rules protect the site's one claim (that every pick is on the record, wins and losses alike):

1. A published pick is never edited. It can be deleted only before its match kicks off.
   After kick-off it can only be settled (won, lost, void with a reason), and it stays.
2. A premium-only pick is hidden from non-members *until kick-off*; from then on everyone can
   see it with its result. Premium sells early access, not a record that shows only the winners.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.account import AuditLog, User
from app.models.content import (
    RESULT_LOST,
    RESULT_PENDING,
    RESULT_VOID,
    RESULT_WON,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    ManualPick,
    Post,
)

SPORTS = ("football", "basketball", "tennis")


class ContentError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


# --- posts --------------------------------------------------------------------------------


def slugify(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    return slug[:100] or "post"


def _unique_slug(db: Session, base: str, exclude_id: int | None = None) -> str:
    slug, n = base, 2
    while True:
        query = db.query(Post.id).filter(Post.slug == slug)
        if exclude_id is not None:
            query = query.filter(Post.id != exclude_id)
        if query.first() is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


def post_view(post: Post, *, include_body: bool = True, locked: bool = False) -> dict:
    return {
        "id": post.id,
        "slug": post.slug,
        "title": post.title,
        "excerpt": post.excerpt,
        "body": post.body if include_body and not locked else "",
        "locked": locked,
        "premium_only": post.premium_only,
        "status": post.status,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
        "published_at": post.published_at.isoformat() if post.published_at else None,
    }


def save_post(
    db: Session,
    *,
    actor: User,
    post_id: int | None,
    title: str,
    excerpt: str,
    body: str,
    premium_only: bool,
    publish: bool,
) -> Post:
    title = (title or "").strip()
    if not title:
        raise ContentError("title_required", "A post needs a title.")
    if len(title) > 160:
        raise ContentError("title_too_long", "Keep the title under 160 characters.")
    if len(body or "") > 100_000:
        raise ContentError("body_too_long", "The post is too long.")
    excerpt = (excerpt or "").strip()[:400]
    if not excerpt:
        if premium_only:
            # The summary is shown to everyone, so it is never copied from a premium body: a
            # short post would be given away whole.
            excerpt = "Members-only analysis. Join premium to read the full post."
        else:
            plain = re.sub(r"[#*_`>\[\]()]", "", body or "").strip().replace("\n", " ")
            excerpt = plain[:200]

    now = _now()
    if post_id is None:
        post = Post(slug=_unique_slug(db, slugify(title)), title=title, author_id=actor.id)
        db.add(post)
        action = "post.create"
    else:
        post = db.get(Post, post_id)
        if post is None:
            raise ContentError("not_found", "That post does not exist.", 404)
        post.updated_at = now
        action = "post.update"
    post.title = title
    post.excerpt = excerpt
    post.body = body or ""
    post.premium_only = bool(premium_only)
    if publish and post.status != STATUS_PUBLISHED:
        post.status = STATUS_PUBLISHED
        post.published_at = now
        action = "post.publish"
    elif not publish and post.status == STATUS_PUBLISHED and post_id is not None:
        # Saving without the publish box keeps it published; unpublish is its own action.
        pass
    db.flush()
    db.add(AuditLog(actor_id=actor.id, action=action, target=f"post:{post.id}", detail=title[:120]))
    return post


def unpublish_post(db: Session, *, actor: User, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise ContentError("not_found", "That post does not exist.", 404)
    post.status = STATUS_DRAFT
    post.published_at = None
    db.add(AuditLog(actor_id=actor.id, action="post.unpublish", target=f"post:{post.id}"))
    return post


def delete_post(db: Session, *, actor: User, post_id: int) -> None:
    post = db.get(Post, post_id)
    if post is None:
        raise ContentError("not_found", "That post does not exist.", 404)
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="post.delete",
            target=f"post:{post.id}",
            detail=post.title[:120],
        )
    )
    db.delete(post)


# --- picks --------------------------------------------------------------------------------


def pick_view(pick: ManualPick, *, viewer_has_premium: bool, now: datetime | None = None) -> dict:
    """The pick as a viewer may see it. A premium pick is redacted before kick-off."""
    now = now or _now()
    started = pick.kickoff <= now
    hidden = (
        pick.status == STATUS_PUBLISHED
        and pick.premium_only
        and not viewer_has_premium
        and not started
    )
    data = {
        "id": pick.id,
        "sport": pick.sport,
        "competition": pick.competition,
        "home_team": pick.home_team,
        "away_team": pick.away_team,
        "kickoff": pick.kickoff.isoformat(),
        "premium_only": pick.premium_only,
        "status": pick.status,
        "result": pick.result,
        "void_reason": pick.void_reason if pick.result == RESULT_VOID else None,
        "published_at": pick.published_at.isoformat() if pick.published_at else None,
        "settled_at": pick.settled_at.isoformat() if pick.settled_at else None,
        "locked": hidden,
    }
    if hidden:
        data.update(
            {"market": None, "selection": None, "odds": None, "confidence": None, "rationale": None}
        )
    else:
        data.update(
            {
                "market": pick.market,
                "selection": pick.selection,
                "odds": pick.odds,
                "confidence": pick.confidence,
                "rationale": pick.rationale,
            }
        )
    return data


def _check_pick_fields(
    *, sport, competition, home_team, away_team, kickoff, market, selection, odds, confidence
) -> None:
    if sport not in SPORTS:
        raise ContentError("bad_sport", "Choose football, basketball or tennis.")
    for label, value in (
        ("competition", competition),
        ("home team", home_team),
        ("away team", away_team),
        ("market", market),
        ("selection", selection),
    ):
        if not (value or "").strip():
            raise ContentError("missing_field", f"The {label} is required.")
    if odds is not None and not (1.01 <= float(odds) <= 1000):
        raise ContentError("bad_odds", "Odds must be a decimal price between 1.01 and 1000.")
    if confidence is not None and not (1 <= int(confidence) <= 100):
        raise ContentError("bad_confidence", "Confidence is a number from 1 to 100.")


def create_pick(
    db: Session,
    *,
    actor: User,
    sport: str,
    competition: str,
    home_team: str,
    away_team: str,
    kickoff: datetime,
    market: str,
    selection: str,
    odds: float | None,
    confidence: int | None,
    rationale: str,
    premium_only: bool,
    publish: bool,
) -> ManualPick:
    _check_pick_fields(
        sport=sport,
        competition=competition,
        home_team=home_team,
        away_team=away_team,
        kickoff=kickoff,
        market=market,
        selection=selection,
        odds=odds,
        confidence=confidence,
    )
    kickoff = _naive_utc(kickoff)
    now = _now()
    if publish and kickoff <= now:
        raise ContentError(
            "already_started",
            "That match has already kicked off. A pick has to be published before kick-off.",
        )
    pick = ManualPick(
        sport=sport,
        competition=competition.strip()[:120],
        home_team=home_team.strip()[:120],
        away_team=away_team.strip()[:120],
        kickoff=kickoff,
        market=market.strip()[:80],
        selection=selection.strip()[:120],
        odds=float(odds) if odds is not None else None,
        confidence=int(confidence) if confidence is not None else None,
        rationale=(rationale or "").strip()[:4000],
        premium_only=bool(premium_only),
        status=STATUS_PUBLISHED if publish else STATUS_DRAFT,
        result=RESULT_PENDING,
        created_by=actor.id,
        published_at=now if publish else None,
    )
    db.add(pick)
    db.flush()
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="pick.publish" if publish else "pick.draft",
            target=f"pick:{pick.id}",
            detail=f"{pick.home_team} v {pick.away_team}: {pick.selection}"[:200],
        )
    )
    return pick


def publish_pick(db: Session, *, actor: User, pick_id: int) -> ManualPick:
    pick = db.get(ManualPick, pick_id)
    if pick is None:
        raise ContentError("not_found", "That pick does not exist.", 404)
    if pick.status == STATUS_PUBLISHED:
        return pick
    now = _now()
    if pick.kickoff <= now:
        raise ContentError(
            "already_started",
            "That match has already kicked off. A pick has to be published before kick-off.",
        )
    pick.status = STATUS_PUBLISHED
    pick.published_at = now
    db.add(AuditLog(actor_id=actor.id, action="pick.publish", target=f"pick:{pick.id}"))
    return pick


def delete_pick(db: Session, *, actor: User, pick_id: int) -> None:
    """Drafts always; a published pick only before its match kicks off."""
    pick = db.get(ManualPick, pick_id)
    if pick is None:
        raise ContentError("not_found", "That pick does not exist.", 404)
    if pick.status == STATUS_PUBLISHED and pick.kickoff <= _now():
        raise ContentError(
            "locked_after_kickoff",
            "This match has kicked off, so the pick stays on the record. "
            "Mark it void with a reason instead.",
            409,
        )
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="pick.delete",
            target=f"pick:{pick.id}",
            detail=f"{pick.home_team} v {pick.away_team}: {pick.selection} ({pick.status})"[:200],
        )
    )
    db.delete(pick)


def settle_pick(
    db: Session, *, actor: User, pick_id: int, result: str, void_reason: str | None = None
) -> ManualPick:
    if result not in (RESULT_WON, RESULT_LOST, RESULT_VOID):
        raise ContentError("bad_result", "The result is won, lost or void.")
    pick = db.get(ManualPick, pick_id)
    if pick is None:
        raise ContentError("not_found", "That pick does not exist.", 404)
    if pick.status != STATUS_PUBLISHED:
        raise ContentError("not_published", "Only a published pick has a result.")
    now = _now()
    if result != RESULT_VOID and pick.kickoff > now:
        raise ContentError("not_started", "The match has not kicked off yet.")
    if pick.result in (RESULT_WON, RESULT_LOST) and result != pick.result:
        # A settled result is final. Correcting a wrong one is a void with a reason, kept visible.
        if result != RESULT_VOID:
            raise ContentError(
                "already_settled", "This pick already has a result. It can only be voided."
            )
    if result == RESULT_VOID and not (void_reason or "").strip():
        raise ContentError("reason_required", "Say why the pick is void.")
    pick.result = result
    pick.void_reason = (void_reason or "").strip()[:200] or None
    pick.settled_at = now
    db.add(
        AuditLog(
            actor_id=actor.id,
            action=f"pick.{result}",
            target=f"pick:{pick.id}",
            detail=(void_reason or "")[:200],
        )
    )
    return pick


def record(db: Session) -> dict:
    """The editor's record: every published pick that has a result, and those still to come."""
    rows = db.query(ManualPick).filter(ManualPick.status == STATUS_PUBLISHED).all()
    won = sum(1 for r in rows if r.result == RESULT_WON)
    lost = sum(1 for r in rows if r.result == RESULT_LOST)
    void = sum(1 for r in rows if r.result == RESULT_VOID)
    pending = sum(1 for r in rows if r.result == RESULT_PENDING)
    settled = won + lost
    return {
        "published": len(rows),
        "won": won,
        "lost": lost,
        "void": void,
        "pending": pending,
        "settled": settled,
        "win_rate": round(100.0 * won / settled, 1) if settled else None,
    }
