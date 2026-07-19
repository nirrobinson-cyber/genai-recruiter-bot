"""Tests for the Main Agent's routing decision. No real API calls — mocked."""

from __future__ import annotations

import pytest

from app.modules.main_agent import agent
from app.schemas import RoutingDecision


def test_route_returns_llm_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent,
        "_call_llm",
        lambda history,
        consultations_so_far,
        last_action,
        qualifying_info_shared,
        slots_already_offered: RoutingDecision(next_step="sched", reason="weekday mentioned"),
    )

    result = agent.route([{"role": "user", "content": "How about next Friday?"}])

    assert result.next_step == "sched"


def test_route_passes_last_action_through_to_the_llm_call(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_call(
        history, consultations_so_far, last_action, qualifying_info_shared, slots_already_offered
    ) -> RoutingDecision:
        seen["last_action"] = last_action
        return RoutingDecision(next_step="sched", reason="phase hint")

    monkeypatch.setattr(agent, "_call_llm", fake_call)

    agent.route([{"role": "user", "content": "april 2024?"}], last_action="schedule")

    assert seen["last_action"] == "schedule"


def test_route_passes_maturity_signals_through_to_the_llm_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_call(
        history, consultations_so_far, last_action, qualifying_info_shared, slots_already_offered
    ) -> RoutingDecision:
        seen["qualifying_info_shared"] = qualifying_info_shared
        seen["slots_already_offered"] = slots_already_offered
        return RoutingDecision(next_step="sched", reason="proactive escalation")

    monkeypatch.setattr(agent, "_call_llm", fake_call)

    agent.route(
        [{"role": "user", "content": "I've been using Python for five years."}],
        qualifying_info_shared=True,
        slots_already_offered=False,
    )

    assert seen == {"qualifying_info_shared": True, "slots_already_offered": False}


def test_route_falls_back_when_llm_call_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def always_fails(
        history, consultations_so_far, last_action, qualifying_info_shared, slots_already_offered
    ) -> RoutingDecision:
        raise RuntimeError("simulated API failure")

    monkeypatch.setattr(agent, "_call_llm", always_fails)

    result = agent.route([{"role": "user", "content": "..."}])

    assert result is agent.FALLBACK
    assert result.next_step == "respond"
