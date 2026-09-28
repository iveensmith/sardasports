"""CLI: index every document in `rag/knowledge_base/` into ChromaDB.

Usage:
    uv run python -m rag.indexer
"""

from __future__ import annotations

import logging

from rag.retriever import index_knowledge_base

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    count = index_knowledge_base()
    logger.info("Indexed %d document chunks into ChromaDB", count)


if __name__ == "__main__":
    main()
