"""AI analyst agent response schema."""

from __future__ import annotations

from pydantic import BaseModel


class ToolCallOut(BaseModel):
    tool: str
    input: dict
    result: dict


class AnalystOut(BaseModel):
    match_id: int
    analysis: str
    tool_calls: list[ToolCallOut]
    model: str
