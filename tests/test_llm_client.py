"""Tests for the LLM response cache (app.llm_client.cached_parse). No real
API calls — a fake client stands in for the OpenAI SDK."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from app import llm_client


class _Decision(BaseModel):
    value: str


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls = 0

    def parse(
        self,
        *,
        model: str,
        temperature: float,
        messages: list[dict],
        response_format: type[_Decision],
    ):
        self.calls += 1

        class _Message:
            parsed = response_format(value=f"call-{self.calls}")

        class _Choice:
            message = _Message()

        class _Completion:
            choices = [_Choice()]

        return _Completion()


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self) -> None:
        self.chat = _FakeChat()


def test_identical_calls_hit_the_cache_not_the_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client = _FakeClient()
    monkeypatch.setattr(llm_client, "get_client", lambda: fake_client)
    messages = [{"role": "system", "content": "hi"}, {"role": "user", "content": "hello"}]

    first = llm_client.cached_parse("gpt-4o-mini", 0.0, messages, _Decision, cache_dir=tmp_path)
    second = llm_client.cached_parse("gpt-4o-mini", 0.0, messages, _Decision, cache_dir=tmp_path)

    assert fake_client.chat.completions.calls == 1
    assert first == second == _Decision(value="call-1")


def test_different_messages_are_not_cached_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client = _FakeClient()
    monkeypatch.setattr(llm_client, "get_client", lambda: fake_client)

    llm_client.cached_parse(
        "gpt-4o-mini", 0.0, [{"role": "user", "content": "a"}], _Decision, cache_dir=tmp_path
    )
    llm_client.cached_parse(
        "gpt-4o-mini", 0.0, [{"role": "user", "content": "b"}], _Decision, cache_dir=tmp_path
    )

    assert fake_client.chat.completions.calls == 2
