"""Tests for the AdvisorOutput Pydantic contracts (GRB-020)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import InfoAdvisorOutput, MainAgentOutput


def test_main_agent_output_rejects_invalid_action() -> None:
    with pytest.raises(ValidationError):
        MainAgentOutput(action="maybe", message="hi")  # type: ignore[arg-type]


def test_main_agent_output_defaults() -> None:
    output = MainAgentOutput(action="continue", message="hi")

    assert output.consulted == []
    assert output.rationale == ""


def test_info_advisor_output_allows_null_draft_answer() -> None:
    output = InfoAdvisorOutput(decision="info_not_needed", reason="no question asked")

    assert output.draft_answer is None
    assert output.sources == []
