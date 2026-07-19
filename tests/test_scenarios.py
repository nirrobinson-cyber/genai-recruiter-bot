"""Real-API scenario tests against actual dataset conversation snippets.

Marked `real_api` — excluded from the default `pytest` run (see
pyproject.toml's `addopts`). Run explicitly:

    pytest -m real_api
    pytest tests/test_scenarios.py

These verify actual LLM routing/advisor behavior against real historical
conversation turns from data/raw/sms_conversations.json — regression
coverage for behavior that can't be meaningfully checked with mocks, since
the whole point is confirming what the real model actually decides.
"""

from __future__ import annotations

import pytest

from app.graph import run_turn
from app.modules.main_agent import agent
from app.state import ConversationState

pytestmark = pytest.mark.real_api


def test_first_experience_mention_does_not_escalate_to_sched() -> None:
    """Conversation 2 turn 3 pattern (data/raw/sms_conversations.json): the
    candidate's FIRST substantive reply shares qualifying experience, but
    the dataset's own gold label for the following turn is "continue" (the
    recruiter asks a follow-up), not "schedule" — the router must not
    escalate on this same turn, only arm the maturity flag for later."""
    history = [
        {
            "role": "assistant",
            "content": "Hi, thanks for submitting your application for our Python Developer role. Could you share a bit about your Python experience?",
        },
        {"role": "user", "content": "I have three years' experience with Django and Flask."},
    ]

    routing = agent.route(history, [], None, False, False)

    assert routing.next_step != "sched"
    assert routing.candidate_shared_experience is True


def test_second_round_with_qualifying_info_armed_escalates_to_sched() -> None:
    """Once qualifying info was already flagged as shared on an earlier turn
    and no slots have been offered yet, the router should proactively
    escalate to "sched" without an explicit scheduling request (conversation
    2's own turn 7 pattern)."""
    history = [
        {
            "role": "assistant",
            "content": "Hi, thanks for submitting your application for our Python Developer role. Could you share a bit about your Python experience?",
        },
        {"role": "user", "content": "I have three years' experience with Django and Flask."},
        {"role": "assistant", "content": "Do you have any questions of your own?"},
        {"role": "user", "content": "Could you share more about the company's cloud technologies?"},
        {"role": "assistant", "content": "We currently deploy to AWS using Docker and ECS."},
        {"role": "user", "content": "Sounds great! I'd be happy to schedule a meeting"},
    ]

    routing = agent.route(history, [], None, True, False)

    assert routing.next_step == "sched"


@pytest.mark.xfail(
    reason=(
        "CORE-REV, deferred 2026-07-19: a deterministic same-turn guard was tried and reverted — it forced 'continue' "
        "uniformly on this turn-shape, but full-dataset eval showed most gold=schedule conversations actually want "
        "IMMEDIATE escalation here (schedule recall dropped 78.9%->31.6%), so blocking it was a net regression, not a "
        "fix. The ground truth is genuinely inconsistent for this exact input across conversations (see CLAUDE.md) — "
        "revisit with a richer signal, not a blanket rule."
    ),
    strict=False,
)
def test_run_turn_defers_escalation_to_the_next_turn_not_same_turn() -> None:
    """Regression test for a same-turn leak: the maturity flag used to be
    armed AND consumed within the same `run_turn` call whenever a same-turn
    re-consult happened (info declines, then a second routing call already
    saw the just-armed flag) — escalating to "schedule" in the very turn
    experience was first mentioned, contradicting the intended "wait for
    the next turn" design (see app/graph.py's `experience_shared_this_turn`)."""
    state = ConversationState()
    state.add_message(
        "assistant",
        "Hi, thanks for submitting your application for our Python Developer role. Could you share a bit about your Python experience?",
    )

    first = run_turn("I have three years' experience with Django and Flask.", state)

    assert first["action"] != "schedule"
    assert state.qualifying_info_shared is True


def test_numeral_years_of_experience_does_not_block_proactive_offer() -> None:
    """Conversation 12 turn 3 pattern: "Yes, 3 years' experience" used to be
    wrongly treated as a garbled date attempt (the bare digit "3") once
    qualifying info was already armed, blocking the proactive nearest-slots
    offer. Confirms the fix end-to-end through the real Sched Advisor."""
    state = ConversationState()
    state.add_message("assistant", "Could you share a bit about your Python experience?")
    state.qualifying_info_shared = True
    state.advisor_outputs.append(
        {"action": "continue", "consulted": ["info"], "message": "...", "slots": []}
    )

    result = run_turn("Yes, 3 years' experience", state)

    assert result["action"] == "schedule"
    assert result["slots"]
