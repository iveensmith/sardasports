# AI Analyst Agent

An LLM tool-calling agent that narrates UniquePredict's predictions in
prose, backed entirely by real tool calls — implemented in Phase 2,
live-verified with a real `ANTHROPIC_API_KEY` (see `docs/roadmap.md`).

## Structure

```
app/agents/
├── tools.py       # tool implementations, each a thin wrapper over an
│                   # already-tested app/services/* function (or ml.prediction)
└── analyst.py       # the Anthropic tool-calling loop + system prompt
```

`app/api/routes_analyst.py` exposes it as `POST /analyst/{match_id}`.

## Tools available to the model

| Tool | Backed by |
|---|---|
| `get_team_form` | `app.services.team_service` |
| `get_recent_matches` | `app.services.team_service` |
| `get_head_to_head` | `ml.feature_engineering.features.compute_head_to_head` |
| `get_model_prediction` | `app.services.prediction_service.predict_for_match` |
| `get_elo_rating` | `app.models.Team.elo_rating` |
| `get_standings` | `app.services.standings_service.compute_standings` (live table from ingested results) |
| `get_injuries` | `app.services.injury_service` (real API-Football data — see below) |
| `retrieve_knowledge` | `rag.retriever.query_knowledge_base` (see `rag/README.md`) |

`get_injuries` reads whatever `scripts/sync_injuries.py` has synced from
API-Football (requires your own `API_FOOTBALL_KEY`, a free tier is
available). For a team that's never been synced, it returns
`available: false` with instructions to run the sync — never a guess — and
the system prompt explicitly instructs the model to relay that honestly.

## Running it

Requires `ANTHROPIC_API_KEY` in **`.env`** (gitignored — never `.env.example`,
which is a committed template) — read via `app.utils.config.get_settings()`,
same as every other credential in this codebase. Without it,
`POST /analyst/{match_id}` returns `503` with a clear message; the rest of
the API is unaffected.

```bash
curl -X POST http://localhost:8000/analyst/1
```

Real output (Southampton vs Arsenal):

```json
{
  "match_id": 1133,
  "analysis": "UniquePredict rates this heavily in Arsenal's favor, giving the Gunners an 82.8% win probability against just 7.1% for Southampton (10.1% draw)... The gap is driven largely by the massive Elo disparity (Arsenal 1724 vs Southampton 1243.7), reinforced by form: Southampton have won none of their last 10 (0.3 pts/game, conceding 18 goals), while Arsenal are unbeaten in 9 of their last 10 with 1.9 pts/game...",
  "tool_calls": [
    {"tool": "get_model_prediction", "input": {"match_id": 1133}, "result": {"...": "..."}},
    {"tool": "get_team_form", "input": {"team": "Southampton"}, "result": {"...": "..."}},
    {"tool": "get_team_form", "input": {"team": "Arsenal"}, "result": {"...": "..."}}
  ],
  "model": "claude-sonnet-5"
}
```

## Why it never fabricates data

Every tool call returns real data from the database/ML pipeline or an
explicit "not available." The system prompt (`SYSTEM_PROMPT` in
`analyst.py`) forbids inventing statistics and requires calling
`get_model_prediction` plus `get_team_form` for both teams before answering.
