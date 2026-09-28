"""ChromaDB-backed retriever for the RAG knowledge base.

Uses a local persistent ChromaDB client by default (no separate service
needed for local dev). When `CHROMA_URL` is set (as `docker-compose.yml`
does for the `api` service, pointing at the `chromadb` container), it
connects to that networked instance instead — same collection name, same
API, just a different backend. Embeddings use Chroma's bundled
all-MiniLM-L6-v2 ONNX model — no API key required, unlike the AI analyst
agent's LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass

import chromadb

from app.utils.config import get_settings
from rag.ingestion.loader import DocumentChunk, load_knowledge_base

COLLECTION_NAME = "football_knowledge"

_client: chromadb.ClientAPI | None = None


def get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        settings = get_settings()
        if settings.chroma_url:
            host, _, port = (
                settings.chroma_url.replace("http://", "").replace("https://", "").partition(":")
            )
            _client = chromadb.HttpClient(host=host, port=int(port) if port else 8000)
        else:
            settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(path=str(settings.chroma_persist_dir))
    return _client


def get_collection():
    return get_client().get_or_create_collection(COLLECTION_NAME)


def index_documents(chunks: list[DocumentChunk]) -> int:
    """Upsert every chunk into the collection. Safe to re-run (upsert, not add)."""
    if not chunks:
        return 0
    collection = get_collection()
    collection.upsert(
        ids=[c.id for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[{"source": c.source, "title": c.title} for c in chunks],
    )
    return len(chunks)


def index_knowledge_base() -> int:
    """Load and index every document under `rag/knowledge_base/`."""
    chunks = load_knowledge_base()
    return index_documents(chunks)


@dataclass
class RetrievedPassage:
    text: str
    source: str
    title: str
    distance: float


def query_knowledge_base(query_text: str, n_results: int = 3) -> list[RetrievedPassage]:
    """Semantic search over the indexed knowledge base. Empty list if nothing is indexed."""
    collection = get_collection()
    if collection.count() == 0:
        return []

    n_results = min(n_results, collection.count())
    results = collection.query(query_texts=[query_text], n_results=n_results)

    passages = []
    for text, metadata, distance in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0], strict=True
    ):
        passages.append(
            RetrievedPassage(
                text=text, source=metadata["source"], title=metadata["title"], distance=distance
            )
        )
    return passages
