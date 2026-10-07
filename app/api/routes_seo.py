"""GET /seo/urls: the pages the website should list in its sitemap."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.seo_service import sitemap_entries

router = APIRouter(tags=["seo"])


@router.get("/seo/urls")
def seo_urls(db: Session = Depends(get_db)) -> dict:
    """League, team and match page slugs with real last-modified dates."""
    return sitemap_entries(db)
