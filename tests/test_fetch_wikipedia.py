"""Tests for rag.ingestion.fetch_wikipedia — mocked HTTP (no network in tests),
plus a real end-to-end check of the loader picking up saved articles."""

from __future__ import annotations

from rag.ingestion.fetch_wikipedia import fetch_extract, select_paragraphs
from rag.ingestion.loader import load_knowledge_base


class FakeResponse:
    def __init__(self, json_data: dict):
        self._json = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def test_fetch_extract_returns_none_for_missing_page(monkeypatch):
    monkeypatch.setattr(
        "rag.ingestion.fetch_wikipedia.requests.get",
        lambda *a, **k: FakeResponse(
            {"query": {"pages": {"-1": {"title": "Nope", "missing": ""}}}}
        ),
    )
    assert fetch_extract("Nope") is None


def test_fetch_extract_returns_title_and_text(monkeypatch):
    monkeypatch.setattr(
        "rag.ingestion.fetch_wikipedia.requests.get",
        lambda *a, **k: FakeResponse(
            {"query": {"pages": {"123": {"title": "Expected goals", "extract": "Some text."}}}}
        ),
    )
    result = fetch_extract("Expected goals")
    assert result == ("Expected goals", "Some text.")


def test_select_paragraphs_skips_headers_and_short_lines():
    long_a = (
        "This is a genuinely long, substantive paragraph that clears the minimum length "
        "threshold easily."
    )
    long_b = (
        "Another sufficiently long paragraph that also clears the minimum length "
        "threshold for inclusion."
    )
    extract = f"== History ==\nShort.\n{long_a}\n\n== See also ==\n{long_b}\n"
    paragraphs = select_paragraphs(extract, max_paragraphs=5)
    assert len(paragraphs) == 2
    assert all("==" not in p for p in paragraphs)
    assert all(len(p) >= 80 for p in paragraphs)


def test_select_paragraphs_respects_max_count():
    long_paragraph = "x" * 100
    extract = "\n".join([long_paragraph] * 20)
    paragraphs = select_paragraphs(extract, max_paragraphs=3)
    assert len(paragraphs) == 3


def test_save_article_writes_attribution_and_content(tmp_path, monkeypatch):
    import rag.ingestion.fetch_wikipedia as fw

    monkeypatch.setattr(fw, "OUTPUT_DIR", tmp_path)
    path = fw.save_article("Expected goals", "Expected goals", ["Paragraph one.", "Paragraph two."])

    content = path.read_text(encoding="utf-8")
    assert content.startswith("# Expected goals")
    assert "CC BY-SA 4.0" in content
    assert "en.wikipedia.org/wiki/Expected_goals" in content
    assert "Paragraph one." in content
    assert "Paragraph two." in content


def test_loader_picks_up_real_saved_wikipedia_articles():
    # Exercises the real files this session fetched into rag/knowledge_base/wikipedia/
    # (via `uv run python -m rag.ingestion.fetch_wikipedia`), not a fixture.
    chunks = load_knowledge_base()
    wikipedia_sources = {c.source for c in chunks if c.source.startswith("wikipedia/")}
    assert any("brier_score" in s for s in wikipedia_sources)
    assert any("expected_goals" in s for s in wikipedia_sources)
