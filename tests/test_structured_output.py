"""Tests for the structured-output retry/fallback helper (GRB-020, rule N-3)."""

from __future__ import annotations

from app.schemas import ExitAdvisorOutput
from app.structured_output import get_structured_output

FALLBACK = ExitAdvisorOutput(decision="dont_end", confidence=0.0, reason="parse failure fallback")


def test_returns_call_result_on_first_success() -> None:
    result = get_structured_output(
        lambda: ExitAdvisorOutput(decision="end", confidence=0.9, reason="candidate opted out"),
        fallback=FALLBACK,
    )

    assert result.decision == "end"


def test_retries_once_then_succeeds() -> None:
    attempts = {"count": 0}

    def flaky_call() -> ExitAdvisorOutput:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ValueError("simulated parse failure")
        return ExitAdvisorOutput(decision="end", confidence=0.8, reason="retried successfully")

    result = get_structured_output(flaky_call, fallback=FALLBACK)

    assert attempts["count"] == 2
    assert result.decision == "end"


def test_falls_back_after_two_failures() -> None:
    def always_fails() -> ExitAdvisorOutput:
        raise ValueError("simulated parse failure")

    result = get_structured_output(always_fails, fallback=FALLBACK)

    assert result is FALLBACK
