"""Tests for the RAG knowledge base (chunking + real ChromaDB retrieval).

Uses a real, temporary ChromaDB collection (not mocked) — these exercise the
actual embedding + query path, just against an isolated persist directory so
they don't touch the project's real `rag/chroma_store/`.
"""

from __future__ import annotations

from rag.ingestion.loader import chunk_markdown, load_knowledge_base


def test_chunk_markdown_drops_the_title_heading():
    text = "# My Title\n\nFirst paragraph.\n\nSecond paragraph."
    chunks = chunk_markdown(text, title="My Title", source="test.md")
    assert len(chunks) == 2
    assert all(c.title == "My Title" for c in chunks)
    assert all(not c.text.startswith("# ") for c in chunks)


def test_chunk_markdown_assigns_stable_ids():
    text = "# T\n\nPara one.\n\nPara two."
    chunks = chunk_markdown(text, title="T", source="doc.md")
    assert chunks[0].id == "doc.md::0"
    assert chunks[1].id == "doc.md::1"


def test_load_knowledge_base_finds_the_real_articles():
    chunks = load_knowledge_base()
    assert len(chunks) > 5
    sources = {c.source for c in chunks}
    assert "elo_ratings.md" in sources
    assert "poisson_goal_models.md" in sources


def test_retrieval_finds_relevant_passage(tmp_path, monkeypatch):
    # Point the retriever at a throwaway persist directory for test isolation,
    # and force the local (non-networked) client regardless of whatever
    # CHROMA_URL happens to be set to in the environment/.env.
    import rag.retriever as retriever_module
    from app.utils.config import get_settings

    monkeypatch.setattr(get_settings(), "chroma_persist_dir", tmp_path / "chroma_test")
    monkeypatch.setattr(get_settings(), "chroma_url", None)
    retriever_module._client = None  # force a fresh client bound to the new path

    count = retriever_module.index_knowledge_base()
    assert count > 5

    results = retriever_module.query_knowledge_base("Elo rating home advantage bonus", n_results=2)
    assert len(results) == 2
    assert any("elo" in r.source.lower() or "home" in r.source.lower() for r in results)

    retriever_module._client = None  # don't leak this test's client into other tests
