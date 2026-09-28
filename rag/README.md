# RAG Knowledge Base

Retrieval-augmented generation over two content sources: original
football-analytics reference articles this project wrote, and real
Wikipedia articles (CC BY-SA 4.0, legitimately reusable with attribution).

## Structure

```
rag/
├── knowledge_base/
│   ├── *.md               # original articles (Elo, Poisson, home advantage,
│   │                       # injury impact, calibration, value-detection)
│   └── wikipedia/          # real third-party content, fetched + attributed
│       └── *.md             # (Expected goals, Elo rating system, Poisson
│                              # distribution, Home advantage, Brier score,
│                              # Sports betting)
├── ingestion/
│   ├── loader.py             # markdown -> paragraph-chunked DocumentChunk list
│   └── fetch_wikipedia.py     # CLI: downloads + attributes real Wikipedia articles
├── retriever.py                # ChromaDB client + index_knowledge_base() + query_knowledge_base()
└── indexer.py                   # CLI: uv run python -m rag.indexer
```

## Workflow

**Question → retrieve context (ChromaDB similarity search) → the AI analyst
agent (`app/agents/analyst.py`) generates its answer grounded in that
context**, via the `retrieve_knowledge` tool — exactly the workflow described
in the master spec.

## Running it

```bash
uv run python -m rag.ingestion.fetch_wikipedia   # (re-)fetch the Wikipedia articles
uv run python -m rag.indexer                     # index everything into ChromaDB
```

Uses a local persistent ChromaDB store (`rag/chroma_store/`, gitignored) by
default — no separate service needed for local dev. In Docker, `CHROMA_URL`
(set automatically by `docker-compose.yml`) points the same code at the
`chromadb` container instead. Embeddings use ChromaDB's bundled
all-MiniLM-L6-v2 model — no API key required (only the AI analyst's own LLM
calls need `ANTHROPIC_API_KEY`).

## Why Wikipedia, and how attribution works

Wikipedia article text is licensed CC BY-SA 4.0, which explicitly permits
reuse with attribution — unlike scraping an arbitrary tactical-analysis site,
this carries no licensing ambiguity. `rag/ingestion/fetch_wikipedia.py` pulls
the plaintext extract for each configured article via Wikipedia's public API,
keeps only the first several substantive paragraphs (skipping section headers
and short fragments), and writes each as `rag/knowledge_base/wikipedia/*.md`
with a source URL, retrieval date, and license notice baked into the file
itself — so every retrieved chunk's origin is traceable.

## Adding more content

- **More Wikipedia articles**: add a title to `ARTICLES` in
  `rag/ingestion/fetch_wikipedia.py` and re-run it.
- **Other real sources**: drop more `.md` files anywhere under
  `rag/knowledge_base/` (one `# Title` heading, then paragraphs, plus a
  source/license line if it's not your own original writing) and re-run the
  indexer — `index_knowledge_base()` upserts, so re-indexing is always safe.
  Whether to scrape a specific non-Wikipedia site is a licensing decision to
  make deliberately per source, not something to default into.
