"""Tests for the Exit Advisor (GRB-024). No real API calls — _call_llm is mocked."""

from __future__ import annotations

import pytest

from app.modules.exit_advisor import advisor
from app.schemas import ExitAdvisorOutput


def test_decide_returns_llm_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        advisor,
        "_call_llm",
        lambda history, model=None: ExitAdvisorOutput(
            decision="end", confidence=0.9, reason="opted out"
        ),
    )

    result = advisor.decide([{"role": "user", "content": "Stop texting me please."}])

    assert result.decision == "end"


def test_decide_falls_back_when_llm_call_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def always_fails(history: list[dict[str, str]], model: str | None = None) -> ExitAdvisorOutput:
        raise RuntimeError("simulated API failure")

    monkeypatch.setattr(advisor, "_call_llm", always_fails)

    result = advisor.decide([{"role": "user", "content": "..."}])

    assert result is advisor.FALLBACK
    assert result.decision == "dont_end"
