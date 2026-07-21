"""Tests for the main-agent turn graph. Advisor/routing decisions are mocked
— no real LLM/DB calls here; each advisor's own logic is tested in its own
test_<advisor>.py file."""

from __future__ import annotations

from datetime import datetime

import pytest

from app import graph
from app.schemas import (
    ExitAdvisorOutput,
    InfoAdvisorOutput,
    RoutingDecision,
    SchedAdvisorOutput,
    SlotProposal,
)
from app.state import ConversationState


def _mock_routing(monkeypatch: pytest.MonkeyPatch, *decisions: RoutingDecision) -> None:
    """Mock main_agent.route to return the given decisions in sequence, one
    per loop iteration (a turn may call it more than once now)."""
    iterator = iter(decisions)
    monkeypatch.setattr(
        graph.main_agent,
        "route",
        lambda history,
        consultations_so_far=None,
        last_action=None,
        qualifying_info_shared=False,
        slots_already_offered=False: next(iterator),
    )


def _mock_info(
    monkeypatch: pytest.MonkeyPatch,
    decision: str = "info_needed",
    draft_answer: str = "Here's the info.",
) -> None:
    monkeypatch.setattr(
        graph.info_advisor,
        "draft_answer",
        lambda history, top_k=3: InfoAdvisorOutput(
            decision=decision, draft_answer=draft_answer, sources=[], reason="mocked"
        ),
    )


def _mock_exit(monkeypatch: pytest.MonkeyPatch, decision: str) -> None:
    monkeypatch.setattr(
        graph.exit_advisor,
        "decide",
        lambda history: ExitAdvisorOutput(decision=decision, confidence=0.9, reason="mocked"),
    )


def _mock_sched(
    monkeypatch: pytest.MonkeyPatch, decision: str, slots: list[SlotProposal] | None = None
) -> None:
    monkeypatch.setattr(
        graph.sched_advisor,
        "decide",
        lambda history, now, offered_slots=None, previously_offered_slots=None: SchedAdvisorOutput(
            decision=decision, proposed_slots=slots or [], reason="mocked"
        ),
    )


def test_run_turn_handles_info_question(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="info", reason="role question"),
        RoutingDecision(next_step="respond", reason="answered"),
    )
    _mock_info(monkeypatch)
    state = ConversationState()

    result = graph.run_turn("What stack do you need for this role?", state)

    assert result["action"] == "continue"
    assert result["consulted"] == ["info"]
    assert result["message"]


def test_run_turn_handles_schedule_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # sched->"sched" is a conclusive verdict, so the loop breaks without a second routing call.
    _mock_routing(monkeypatch, RoutingDecision(next_step="sched", reason="weekday mentioned"))
    _mock_sched(
        monkeypatch,
        "sched",
        slots=[SlotProposal(schedule_id=1, date="2024-04-18", time="10:00:00")],
    )
    state = ConversationState()

    result = graph.run_turn("Can we schedule tomorrow?", state)

    assert result["action"] == "schedule"
    assert result["consulted"] == ["sched"]
    assert result["slots"]
    assert "2024-04-18" in result["message"]
    assert "10:00:00" in result["message"]


def test_run_turn_next_friday_routes_to_sched_not_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test for the exact bug hit manually: a weekday mention with
    no scheduling keyword must route to sched, not fall through to info."""
    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="sched", reason="weekday mentioned, no keyword needed"),
    )
    _mock_sched(
        monkeypatch,
        "sched",
        slots=[SlotProposal(schedule_id=1, date="2024-04-19", time="10:00:00")],
    )
    state = ConversationState()

    result = graph.run_turn("How about next Friday?", state)

    assert result["action"] == "schedule"
    assert result["consulted"] == ["sched"]


def test_run_turn_after_slot_offer_ambiguous_reply_prefers_sched_over_info_decline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for the exact reported bug: right after a slot offer,
    "april 2024?" got routed partly to info (which correctly declined) and
    the generic info-decline fallback won over a more relevant sched
    clarification. The last turn's action ("schedule") must make the sched
    verdict win the synthesis, even though sched also declined (unresolved
    date) — a phase-aware clarification, not a random generic message."""

    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="sched", reason="date mentioned"),
        RoutingDecision(next_step="info", reason="unclear, try info"),
        RoutingDecision(next_step="respond", reason="done"),
    )
    _mock_sched(monkeypatch, "dont_sched")
    _mock_info(monkeypatch, decision="info_not_needed", draft_answer=None)
    state = ConversationState()
    # Simulate the prior turn having just offered slots.
    state.advisor_outputs.append(
        {
            "action": "schedule",
            "consulted": ["sched"],
            "message": "I can offer a few interview slots.",
            "slots": [],
        }
    )

    result = graph.run_turn("april 2024?", state)

    assert result["action"] == "continue"
    assert "day or date" in result["message"]


def test_run_turn_after_slot_offer_ambiguous_reply_restates_the_actual_offered_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for the exact reported bug: after slots were offered,
    asking a clarifying question like "when" got a vague generic re-ask
    ("which day or date works best") instead of the actual dates already
    retrieved from the DB and shown nowhere in the conversation. Once real
    offered slots exist on state, the re-ask must restate them."""

    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="sched", reason="asking about the offer"),
        RoutingDecision(next_step="respond", reason="done"),
    )
    _mock_sched(monkeypatch, "dont_sched")
    state = ConversationState()
    state.advisor_outputs.append(
        {
            "action": "schedule",
            "consulted": ["sched"],
            "message": "I can offer these interview times: 2024-04-16 at 09:00:00. Which works best for you?",
            "slots": [{"schedule_id": 7, "date": "2024-04-16", "time": "09:00:00"}],
        }
    )

    result = graph.run_turn("when", state)

    assert result["action"] == "continue"
    assert "2024-04-16" in result["message"]
    assert "09:00:00" in result["message"]
    assert result["slots"] == [{"schedule_id": 7, "date": "2024-04-16", "time": "09:00:00"}]


def test_run_turn_second_consecutive_continue_still_restates_offered_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for the exact reported bug: after an offer, "when"
    correctly restated the slots (action=continue), but a THIRD message in
    the same open thread (e.g. an unparseable date) lost the offer context
    entirely — because the phase hint fed to routing, and the offered-slots
    lookup, only ever looked at the single immediately-preceding turn, which
    by then was already `continue`, not `schedule`."""

    seen_phase_hints: list[str | None] = []

    def fake_route(
        history,
        consultations_so_far=None,
        last_action=None,
        qualifying_info_shared=False,
        slots_already_offered=False,
    ) -> RoutingDecision:
        seen_phase_hints.append(last_action)
        return RoutingDecision(next_step="sched", reason="date-like reply")

    monkeypatch.setattr(graph.main_agent, "route", fake_route)
    _mock_sched(monkeypatch, "dont_sched")
    state = ConversationState()
    state.advisor_outputs.append(
        {
            "action": "schedule",
            "consulted": ["sched"],
            "message": "I can offer these interview times: 2024-04-16 at 09:00:00. Which works best for you?",
            "slots": [{"schedule_id": 7, "date": "2024-04-16", "time": "09:00:00"}],
        }
    )
    state.advisor_outputs.append(
        {
            "action": "continue",
            "consulted": ["sched"],
            "message": "Here are the times I have available: 2024-04-16 at 09:00:00. Which one works, or let me know another day?",
            "slots": [{"schedule_id": 7, "date": "2024-04-16", "time": "09:00:00"}],
        }
    )

    result = graph.run_turn("hmm, not sure about that one", state)

    assert (
        seen_phase_hints[0] == "schedule"
    )  # phase hint stayed "schedule", not the literal "continue"
    assert result["action"] == "continue"
    assert "2024-04-16" in result["message"]


def test_run_turn_now_override_reaches_sched_advisor(monkeypatch: pytest.MonkeyPatch) -> None:
    """The eval replay harness needs to pin `now` per conversation (spec §9,
    A-5) instead of settings.now() — confirm run_turn actually threads it
    through to sched_advisor.decide."""
    seen: dict[str, object] = {}

    def fake_decide(
        history: list[dict[str, str]],
        now: datetime,
        offered_slots: list[dict] | None = None,
        previously_offered_slots: list[dict] | None = None,
    ) -> SchedAdvisorOutput:
        seen["now"] = now
        return SchedAdvisorOutput(decision="sched", proposed_slots=[], reason="mocked")

    _mock_routing(monkeypatch, RoutingDecision(next_step="sched", reason="date mentioned"))
    monkeypatch.setattr(graph.sched_advisor, "decide", fake_decide)
    state = ConversationState()
    override = datetime(2024, 4, 3, 15, 12, 0)

    graph.run_turn("Can we schedule tomorrow?", state, now=override)

    assert seen["now"] == override


def test_run_turn_sched_confirmed_ends_with_booking_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pattern 2: confirming a previously offered slot is a terminal booking
    path, separate from the Exit Advisor (which stays disinterest-only)."""
    _mock_routing(monkeypatch, RoutingDecision(next_step="sched", reason="confirming a time"))
    _mock_sched(
        monkeypatch,
        "confirmed",
        slots=[SlotProposal(schedule_id=42, date="2024-04-22", time="15:00:00")],
    )
    state = ConversationState()
    state.advisor_outputs.append(
        {
            "action": "schedule",
            "consulted": ["sched"],
            "message": "I can offer a few interview slots.",
            "slots": [{"schedule_id": 42, "date": "2024-04-22", "time": "15:00:00"}],
        }
    )

    result = graph.run_turn("Monday at 3 PM is good.", state)

    assert result["action"] == "end"
    assert "2024-04-22" in result["message"]
    assert "15:00:00" in result["message"]


def test_run_turn_sets_qualifying_info_shared_and_threads_it_to_next_routing_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pattern 1: the proactive-escalation flag is sticky on state and gets
    passed into the routing call (mechanical plumbing check; the actual
    "does the model proactively offer" question is an eval concern)."""
    seen_flags: list[bool] = []

    def fake_route(
        history,
        consultations_so_far=None,
        last_action=None,
        qualifying_info_shared=False,
        slots_already_offered=False,
    ):
        seen_flags.append(qualifying_info_shared)
        if not qualifying_info_shared:
            return RoutingDecision(
                next_step="respond", reason="ack", candidate_shared_experience=True
            )
        return RoutingDecision(next_step="sched", reason="proactive offer")

    monkeypatch.setattr(graph.main_agent, "route", fake_route)
    _mock_sched(
        monkeypatch,
        "sched",
        slots=[SlotProposal(schedule_id=1, date="2024-04-18", time="10:00:00")],
    )
    state = ConversationState()

    graph.run_turn("I've been using Python for five years.", state)
    assert state.qualifying_info_shared is True

    graph.run_turn("Anything else I should know?", state)
    assert seen_flags[-1] is True


def test_run_turn_sched_routed_but_advisor_says_dont_sched(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="sched", reason="mentioned scheduling"),
        RoutingDecision(next_step="respond", reason="done"),
    )
    _mock_sched(monkeypatch, "dont_sched")
    state = ConversationState()

    result = graph.run_turn("Can we schedule tomorrow?", state)

    assert result["action"] == "continue"
    assert result["consulted"] == ["sched"]
    assert result["slots"] == []


def test_run_turn_handles_exit_request(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_routing(monkeypatch, RoutingDecision(next_step="exit", reason="disinterest"))
    _mock_exit(monkeypatch, "end")
    state = ConversationState()

    result = graph.run_turn("No thanks, stop texting me", state)

    assert result["action"] == "end"
    assert result["consulted"] == ["exit"]


def test_run_turn_exit_routed_but_advisor_says_dont_end(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="exit", reason="might be disinterest"),
        RoutingDecision(next_step="respond", reason="done"),
    )
    _mock_exit(monkeypatch, "dont_end")
    state = ConversationState()

    result = graph.run_turn("No thanks, not right now", state)

    assert result["action"] == "continue"
    assert result["consulted"] == ["exit"]


def test_run_turn_keeps_state_across_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="info", reason="q1"),
        RoutingDecision(next_step="respond", reason="answered"),
        RoutingDecision(next_step="info", reason="q2"),
        RoutingDecision(next_step="respond", reason="answered"),
    )
    _mock_info(monkeypatch)
    state = ConversationState()

    first = graph.run_turn("What stack do you need?", state)
    second = graph.run_turn("What about remote work?", state)

    assert first["action"] == "continue"
    assert second["action"] == "continue"
    assert len(state.history) == 4
    # consult_count is per-turn (guard R-1), reset once each turn completes —
    # it must never accumulate across separate turns.
    assert state.consult_count == 0


def test_run_turn_second_info_question_nudges_towards_scheduling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="info", reason="q1"),
        RoutingDecision(next_step="respond", reason="answered"),
        RoutingDecision(next_step="info", reason="q2"),
        RoutingDecision(next_step="respond", reason="answered"),
    )
    _mock_info(monkeypatch)
    state = ConversationState()

    graph.run_turn("What stack do you need?", state)
    second = graph.run_turn("What about remote work?", state)

    assert "already discussed" in second["message"]


def test_run_turn_returns_a_per_advisor_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    """GRB-043: the terminal loop prints a trace of which advisors were
    consulted and their verdicts — confirm run_turn actually reports it,
    including a case where two different advisors get consulted in one turn."""
    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="sched", reason="date mentioned"),
        RoutingDecision(next_step="info", reason="unclear, try info"),
        RoutingDecision(next_step="respond", reason="done"),
    )
    _mock_sched(monkeypatch, "dont_sched")
    _mock_info(monkeypatch, decision="info_not_needed", draft_answer=None)
    state = ConversationState()

    result = graph.run_turn("hmm", state)

    assert result["trace"] == [
        {"advisor": "sched", "decision": "dont_sched", "reason": "mocked", "slots": []},
        {"advisor": "info", "decision": "info_not_needed", "reason": "mocked", "sources": []},
    ]


def test_run_turn_meaningless_input_skips_advisors_and_asks_to_clarify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reported bug: a stray single-char keystroke ("f") got routed to Info
    and produced a near-duplicate of the previous answer instead of a short
    clarification. No advisor should be consulted at all for input this
    short/meaningless."""

    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("no advisor/routing call should happen for meaningless input")

    monkeypatch.setattr(graph.main_agent, "route", fail_if_called)
    state = ConversationState()

    result = graph.run_turn("f", state)

    assert result["action"] == "continue"
    assert result["consulted"] == []
    assert result["trace"] == []
    assert "say a bit more" in result["message"]


@pytest.mark.parametrize("message", ["", "   ", "x", "zz"])
def test_run_turn_meaningless_input_variants(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    monkeypatch.setattr(
        graph.main_agent,
        "route",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    state = ConversationState()

    result = graph.run_turn(message, state)

    assert result["consulted"] == []


@pytest.mark.parametrize("message", ["5", "ok", "no", "yes"])
def test_run_turn_short_but_meaningful_input_still_reaches_an_advisor(
    monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    """Guards against the meaningless-input check overreaching — a bare
    number (e.g. answering "years of experience?") or a plain yes/no/ok must
    still be routed normally, not swallowed as noise."""
    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="info", reason="short reply"),
        RoutingDecision(next_step="respond", reason="done"),
    )
    _mock_info(monkeypatch)
    state = ConversationState()

    result = graph.run_turn(message, state)

    assert result["consulted"] == ["info"]


def test_run_turn_guard_stops_loop_after_limit() -> None:
    state = ConversationState()
    state.consult_count = 3

    result = graph.run_turn("What else should I know?", state)

    assert result["action"] == "continue"
    assert result["consulted"] == ["guard"]


def test_run_turn_guard_does_not_trip_across_separate_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: the guard must cap consultations *within* a turn,
    not the number of turns in the whole conversation (previously it never
    reset, so the 4th message in any conversation always tripped it)."""

    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="info", reason="q1"),
        RoutingDecision(next_step="respond", reason="a1"),
        RoutingDecision(next_step="info", reason="q2"),
        RoutingDecision(next_step="respond", reason="a2"),
        RoutingDecision(next_step="sched", reason="q3"),
        RoutingDecision(next_step="info", reason="q4"),
        RoutingDecision(next_step="respond", reason="a4"),
        RoutingDecision(next_step="info", reason="q5"),
        RoutingDecision(next_step="respond", reason="a5"),
    )
    _mock_info(monkeypatch)
    _mock_sched(
        monkeypatch,
        "sched",
        slots=[SlotProposal(schedule_id=1, date="2024-04-18", time="10:00:00")],
    )
    state = ConversationState()
    messages = [
        "What stack do you need?",
        "What about remote work?",
        "Can we schedule tomorrow?",
        "Actually, what about compensation?",
        "One more: is it remote-friendly?",
    ]

    results = [graph.run_turn(message, state) for message in messages]

    assert all(result["consulted"] != ["guard"] for result in results)


def test_run_turn_sched_deferral_holds_across_a_same_turn_re_consult(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for the "double-consult inconsistency" bug: the first
    routing call decides NOT to escalate to sched yet (first-time qualifying
    experience, "wait one more exchange" rule — candidate_shared_experience
    is still reported so the flag arms for next turn), consults info, which
    declines. A second routing call within the SAME turn must not flip to
    "sched" just because it now has more context — the "wait" decision holds
    for the rest of this turn. Sched must never be consulted at all."""

    _mock_routing(
        monkeypatch,
        RoutingDecision(
            next_step="info", reason="specific tech, defer", candidate_shared_experience=True
        ),
        RoutingDecision(next_step="sched", reason="flip-flopped after the info decline"),
    )
    _mock_info(monkeypatch, decision="info_not_needed", draft_answer=None)

    def _fail_if_consulted(history, now, offered_slots=None, previously_offered_slots=None):
        raise AssertionError("sched must not be consulted once deferred this turn")

    monkeypatch.setattr(graph.sched_advisor, "decide", _fail_if_consulted)
    state = ConversationState()

    result = graph.run_turn("I have three years' experience with Django and Flask.", state)

    assert result["action"] != "schedule"
    assert state.qualifying_info_shared is True


def test_run_turn_respects_re_consult_guard_within_a_single_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop must stop at MAX_ADVISOR_CONSULTS *within one turn* even if
    routing never says "respond" (e.g. it keeps asking for another advisor)."""

    _mock_routing(
        monkeypatch,
        RoutingDecision(next_step="info", reason="1"),
        RoutingDecision(next_step="info", reason="2"),
        RoutingDecision(next_step="info", reason="3"),
        RoutingDecision(next_step="info", reason="4"),  # would be a 4th call if not capped
    )
    _mock_info(monkeypatch, decision="info_not_needed", draft_answer=None)
    state = ConversationState()

    result = graph.run_turn("hmm", state)

    assert state.consult_count == 0  # reset after the turn
    assert result["consulted"] == ["info", "info", "info"]
