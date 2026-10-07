"""POST /contact: store a message sent through the Contact page."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.contact_service import TOPICS, ContactError, RateLimited, submit

router = APIRouter(tags=["contact"])


class ContactIn(BaseModel):
    # Every field may be missing or null: a form with nothing chosen sends exactly
    # that, and the answer should be our own per-field message ("Choose what your
    # message is about"), not a generic schema error the page cannot show.
    topic: str | None = Field(default="", max_length=40)
    name: str | None = Field(default=None, max_length=400)
    email: str | None = Field(default="", max_length=400)
    message: str | None = Field(default="", max_length=20000)
    # A field no person sees. Anything in it means a bot filled the form in.
    website: str | None = Field(default=None, max_length=400)


@router.get("/contact/topics")
def contact_topics() -> dict:
    """What a message can be about, so the page and the API cannot disagree."""
    return {"topics": [{"value": key, "label": label} for key, label in TOPICS.items()]}


@router.post("/contact")
def send_contact_message(
    body: ContactIn,
    request: Request,
    db: Session = Depends(get_db),
    x_contact_client: str | None = Header(default=None),
) -> dict:
    # The website sends an opaque per-visitor token. Without one (a direct call)
    # the caller's own address is the key. Either way it is used only to count.
    client_key = x_contact_client or (request.client.host if request.client else "unknown")
    try:
        submit(
            db,
            topic=body.topic,
            name=body.name,
            email=body.email,
            message=body.message,
            honeypot=body.website,
            client_key=client_key[:128],
        )
    except ContactError as error:
        raise HTTPException(status_code=422, detail={"errors": error.errors}) from error
    except RateLimited as error:
        raise HTTPException(
            status_code=429,
            detail="Too many messages for now. Please try again in an hour.",
        ) from error
    # The same answer whether the message was kept or a bot was dropped.
    return {"ok": True}
