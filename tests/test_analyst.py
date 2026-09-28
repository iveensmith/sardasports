"""Tests for app.agents.analyst — the agent config/wiring, not real LLM calls.

Regression coverage for a real bug: the agent used to read
ANTHROPIC_API_KEY via raw os.environ.get(...), which pydantic-settings'
`.env`-file loading never populates (it merges `.env` values into the
`Settings` model directly, without exporting them to the process
environment) — so a key that only existed in `.env` was invisible to that
code path even though every other credential in this codebase correctly
goes through `Settings`. These tests mock the Anthropic client (a real call
needs a network + billing, which doesn't belong in the test suite) but
exercise the real `generate_analysis` credential-resolution logic.
"""

from __future__ import annotations

import pytest

import app.agents.analyst as analyst_module
from app.agents.analyst import AgentNotConfiguredError, generate_analysis


class FakeSettingsWithKey:
    anthropic_api_key = "sk-ant-fake-test-key"
    analyst_model = "claude-sonnet-5"


class FakeSettingsNoKey:
    anthropic_api_key = None
    analyst_model = "claude-sonnet-5"


class FakeTextBlock:
    type = "text"
    text = "Arsenal are favoured based on form and Elo."


class FakeResponse:
    content = [FakeTextBlock()]


class FakeMessages:
    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        return FakeResponse()


class FakeAnthropicClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.messages = FakeMessages()


def test_raises_not_configured_when_settings_has_no_key(db_session, monkeypatch):
    monkeypatch.setattr(analyst_module, "get_settings", lambda: FakeSettingsNoKey())
    with pytest.raises(AgentNotConfiguredError):
        generate_analysis(db_session, match_id=1, home_team="Arsenal", away_team="Chelsea")


def test_uses_key_from_settings_not_os_environ(db_session, monkeypatch):
    """The core regression case: a key present ONLY via get_settings() (i.e.
    only in .env, never exported to os.environ) must still be picked up."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # deliberately absent from os.environ
    monkeypatch.setattr(analyst_module, "get_settings", lambda: FakeSettingsWithKey())

    captured_client = {}

    class SpyAnthropicClient(FakeAnthropicClient):
        def __init__(self, api_key: str):
            super().__init__(api_key)
            captured_client["api_key"] = api_key

    fake_anthropic_module = type("module", (), {"Anthropic": SpyAnthropicClient})
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_anthropic_module)

    result = generate_analysis(db_session, match_id=1, home_team="Arsenal", away_team="Chelsea")

    assert captured_client["api_key"] == "sk-ant-fake-test-key"
    assert result.model == "claude-sonnet-5"
    assert "Arsenal" in result.analysis
