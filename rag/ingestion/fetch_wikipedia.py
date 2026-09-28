"""Fetch real, legitimately-licensed third-party content for the RAG knowledge base.

Wikipedia article text is CC BY-SA 4.0 — reusable with attribution, which
this script adds automatically to every article it saves. This is the
project's answer to "index real third-party content" without a scraping
licensing question: Wikipedia explicitly permits this use.

Saves each article as `rag/knowledge_base/wikipedia/{slug}.md`, trimmed to
the first several substantive paragraphs (skipping section headers and
short/list-like lines) so each indexed chunk stays topically focused rather
than pulling in trivia sections, tables, or reference lists.

Usage:
    uv run python -m rag.ingestion.fetch_wikipedia
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "UniquePredict/1.0 (football prediction research project; RAG knowledge base)"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "knowledge_base" / "wikipedia"
MAX_PARAGRAPHS = 8
MIN_PARAGRAPH_LENGTH = 80  # skip short fragments/list items, keep substantive prose

# Articles relevant to the prediction methodology this project documents in
# rag/knowledge_base/*.md — chosen to complement, not duplicate, that
# original content.
ARTICLES = [
    "Expected goals",
    "Elo rating system",
    "Poisson distribution",
    "Home advantage",
    "Brier score",
    "Sports betting",
]


def fetch_extract(title: str) -> tuple[str, str] | None:
    """Return (resolved_title, plaintext_extract) or None if the page doesn't exist."""
    response = requests.get(
        WIKIPEDIA_API,
        params={
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "explaintext": 1,
            "titles": title,
            "redirects": 1,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    pages = response.json()["query"]["pages"]
    page = next(iter(pages.values()))

    if "missing" in page:
        logger.warning("Wikipedia article not found: '%s'", title)
        return None
    return page["title"], page.get("extract", "")


def select_paragraphs(extract: str, max_paragraphs: int = MAX_PARAGRAPHS) -> list[str]:
    """Plaintext extracts include section headers ("== History ==") and short
    list fragments — keep only substantive prose paragraphs, in order."""
    selected = []
    for line in extract.split("\n"):
        line = line.strip()
        if not line or line.startswith("=="):
            continue
        if len(line) < MIN_PARAGRAPH_LENGTH:
            continue
        selected.append(line)
        if len(selected) >= max_paragraphs:
            break
    return selected


def save_article(title: str, resolved_title: str, paragraphs: list[str]) -> Path:
    slug = resolved_title.lower().replace(" ", "_")
    url = f"https://en.wikipedia.org/wiki/{resolved_title.replace(' ', '_')}"
    retrieved = datetime.now(UTC).strftime("%Y-%m-%d")

    body = "\n\n".join(paragraphs)
    content = (
        f"# {resolved_title}\n\n"
        f'Source: Wikipedia, "{resolved_title}" ({url}), retrieved {retrieved}. '
        f"Text licensed under CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/); "
        f"this excerpt is trimmed to its most substantive introductory paragraphs.\n\n"
        f"{body}\n"
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{slug}.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def main() -> None:
    saved = 0
    for title in ARTICLES:
        result = fetch_extract(title)
        if result is None:
            continue
        resolved_title, extract = result
        paragraphs = select_paragraphs(extract)
        if not paragraphs:
            logger.warning("No substantive paragraphs extracted for '%s'", title)
            continue
        path = save_article(title, resolved_title, paragraphs)
        logger.info("Saved %s (%d paragraphs) -> %s", resolved_title, len(paragraphs), path)
        saved += 1

    logger.info("Fetched %d/%d Wikipedia articles", saved, len(ARTICLES))


if __name__ == "__main__":
    main()
