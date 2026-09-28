"""AI football analyst agent — LLM tool-calling over real, service-backed data.

The system prompt explicitly forbids inventing numbers not returned by a
tool call, and every tool is a thin wrapper over an already-tested service
(`app/agents/tools.py`). If a tool can't answer (e.g. `get_injuries` for a
team with no synced data), it says so honestly and the model is instructed
to relay that rather than paper over it.

Requires `ANTHROPIC_API_KEY` (read via `app.utils.config.get_settings`, not
raw `os.environ` — pydantic-settings loads `.env` into the `Settings` model
without exporting it to the process environment, so this must go through
`Settings` like every other credential in this codebase, not
`os.environ.get(...)`, or a key that only exists in `.env` is invisible).
If it's not set, calling `generate_analysis` raises `AgentNotConfiguredError`
— callers (the `/analyst/{match_id}` endpoint) turn that into a clear 503,
never a crash.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agents.tools import TOOL_DEFINITIONS, TOOL_DISPATCH, ToolError
from app.utils.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = """You are UniquePredict's football analyst. You explain match predictions \
using ONLY data returned by your tools — you must never invent a statistic, a form result, \
an Elo rating, or an injury that no tool call returned. If get_injuries reports \
available=false for a team, say plainly that no injury data has been synced for it; do not \
guess or assume that means the team is fully fit. Always call get_model_prediction for the \
match being discussed and at least get_team_form for both teams before answering. Write 2-4 \
sentences, citing the concrete numbers the tools returned (form, Elo, head-to-head, the \
model's probabilities), in the style of a concise professional match-preview analyst."""


class AgentNotConfiguredError(Exception):
    """Raised when ANTHROPIC_API_KEY isn't set — the agent needs the caller's own key."""


@dataclass
class AnalystResult:
    analysis: str
    tool_calls: list[dict] = field(default_factory=list)
    model: str = ""


def _run_tool(session: Session, name: str, tool_input: dict) -> dict:
    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        return {"error": f"Unknown tool '{name}'"}
    try:
        return fn(session, **tool_input)
    except ToolError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - a tool failure must not crash the agent loop
        logger.exception("Tool %s failed", name)
        return {"error": f"Tool failed: {exc}"}


def generate_analysis(
    session: Session, match_id: int, home_team: str, away_team: str
) -> AnalystResult:
    """Run the tool-calling loop and return the analyst's narrative for one match."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise AgentNotConfiguredError(
            "ANTHROPIC_API_KEY is not set — the AI analyst agent needs your own Anthropic API "
            "key to run. Add it to .env and restart the API."
        )
    model = settings.analyst_model

    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - anthropic is a declared dependency
        raise AgentNotConfiguredError("The 'anthropic' package is not installed.") from exc

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Analyze the upcoming match: {home_team} (home) vs {away_team} (away), "
                f"match_id={match_id}."
            ),
        }
    ]
    tool_calls_made: list[dict] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            text = "".join(b.text for b in response.content if b.type == "text")
            return AnalystResult(analysis=text.strip(), tool_calls=tool_calls_made, model=model)

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
            result = _run_tool(session, block.name, block.input)
            tool_calls_made.append({"tool": block.name, "input": block.input, "result": result})
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return AnalystResult(
        analysis="The analyst could not reach a final answer within the tool-call budget.",
        tool_calls=tool_calls_made,
        model=model,
    )
