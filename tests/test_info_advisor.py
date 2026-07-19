"""Tests for the Info Advisor (GRB-021). No real API/vector calls — mocked."""

from __future__ import annotations

import pytest

from app.modules.info_advisor import advisor
from app.schemas import InfoAdvisorOutput


def _history(question: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": question}]


def test_draft_answer_returns_llm_result_when_context_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        advisor,
        "retrieve_context",
        lambda question, top_k: {"documents": ["Uses Django and PostgreSQL."], "ids": ["chunk-1"]},
    )
    monkeypatch.setattr(
        advisor,
        "_call_llm",
        lambda history, documents, sources: InfoAdvisorOutput(
            decision="info_needed",
            draft_answer="We use Django and PostgreSQL.",
            sources=["chunk-1"],
            reason="grounded",
        ),
    )

    result = advisor.draft_answer(_history("What stack do you use?"))

    assert result.decision == "info_needed"
    assert result.sources == ["chunk-1"]


def test_draft_answer_falls_back_to_heuristic_when_llm_call_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        advisor,
        "retrieve_context",
        lambda question, top_k: {"documents": ["Uses Django and PostgreSQL."], "ids": ["chunk-1"]},
    )

    def always_fails(history, documents, sources) -> InfoAdvisorOutput:
        raise RuntimeError("simulated API failure")

    monkeypatch.setattr(advisor, "_call_llm", always_fails)

    result = advisor.draft_answer(_history("What stack do you use?"))

    assert result.decision == "info_needed"
    assert "Django and PostgreSQL" in result.draft_answer


def test_draft_answer_fallback_when_no_context_and_llm_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        advisor, "retrieve_context", lambda question, top_k: {"documents": [], "ids": []}
    )

    def always_fails(history, documents, sources) -> InfoAdvisorOutput:
        raise RuntimeError("simulated API failure")

    monkeypatch.setattr(advisor, "_call_llm", always_fails)

    result = advisor.draft_answer(_history("Are you hiring remote?"))

    assert result.decision == "info_not_needed"
