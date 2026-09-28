"""Markdown document loader/chunker for the RAG knowledge base.

Splits each `.md` file in `rag/knowledge_base/` into paragraph-sized chunks
(a reasonable default granularity for short reference articles like these —
fine enough for specific retrieval, coarse enough to keep each chunk
coherent on its own). Each chunk carries the source filename and the
document's title as metadata, so retrieval results can always be attributed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"


@dataclass
class DocumentChunk:
    id: str
    text: str
    source: str
    title: str


def _extract_title(markdown_text: str) -> str:
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return "Untitled"


def chunk_markdown(text: str, title: str, source: str) -> list[DocumentChunk]:
    """Split on blank lines, dropping the title heading and empty fragments."""
    paragraphs = [p.strip() for p in text.split("\n\n")]
    chunks = []
    index = 0
    for paragraph in paragraphs:
        if not paragraph or paragraph.startswith("# "):
            continue
        chunks.append(
            DocumentChunk(
                id=f"{source}::{index}",
                text=paragraph,
                source=source,
                title=title,
            )
        )
        index += 1
    return chunks


def load_knowledge_base(directory: Path = KNOWLEDGE_BASE_DIR) -> list[DocumentChunk]:
    """Load and chunk every `.md` file in `directory`, recursively (e.g. picks
    up `wikipedia/*.md` alongside the top-level original articles)."""
    if not directory.exists():
        raise SystemExit(f"Knowledge base directory not found: {directory}")

    all_chunks: list[DocumentChunk] = []
    for path in sorted(directory.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = _extract_title(text)
        source = str(path.relative_to(directory)).replace("\\", "/")
        all_chunks.extend(chunk_markdown(text, title=title, source=source))
    return all_chunks
