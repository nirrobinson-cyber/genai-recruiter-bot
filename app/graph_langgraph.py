"""Turn graph — LangGraph `StateGraph` implementation (spec §3.3, §4, GRB-041).

A second, side-by-side implementation of the exact same turn-flow contract as
`app.graph` (the original plain-Python control flow). Selected via
`settings.turn_engine` (see `app.turn_engine`) — `app.graph` stays the
default and is completely untouched by this module.

Design choice for safety, not brevity: this module does NOT reimplement the
advisor-dispatch/synthesis business logic. It imports `app.graph`'s private
helpers (`_looks_meaningless`, `_in_schedule_phase`, `_pending_offered_slots`,
`_synthesize`, ...) and reuses them verbatim. Only the *orchestration*
— the "which advisor next, loop until guard R-1 or a conclusive verdict"
control flow — is re-expressed as LangGraph nodes/conditional edges. This
means the two engines are guaranteed to produce byte-identical messages and
synthesis behavior for the same advisor verdicts; only the mechanism that
decides which advisor(s) run, and in what order, differs.

Graph shape:
    START -> route -[exit/sched/info]-> <advisor node> -[loop]-> route
                   -[respond/guard]-------------------------------> END

`route` mirrors the legacy `while` loop's top-of-iteration check (guard R-1:
stop once `consult_count >= MAX_ADVISOR_CONSULTS`) plus the Main Agent's
routing call and the same-turn `sched_deferred_this_turn` /
`experience_shared_this_turn` bookkeeping (spec §5.1, the "double-consult
inconsistency" fix). Each advisor node increments `consult_count`, records
its verdict/trace entry, and reports whether its verdict was conclusive
(exit->end, sched->sched/confirmed) — conclusive means stop, inconclusive
means loop back to `route` for another consult (up to the guard).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.graph import (
    MAX_ADVISOR_CONSULTS,
    _in_schedule_phase,
    _last_action,
    _looks_meaningless,
    _pending_offered_slots,
    _slots_already_offered,
    _synthesize,
)
from app.modules.exit_advisor import advisor as exit_advisor
from app.modules.info_advisor import advisor as info_advisor
from app.modules.main_agent import agent as main_agent
from app.modules.sched_advisor import advisor as sched_advisor
from app.schemas import MainAgentOutput
from app.state import ConversationState

_RECURSION_LIMIT = 50  # generous headroom over guard R-1's real cap (see module docstring)


class TurnState(TypedDict, total=False):
    """Per-turn scratch state threaded through the graph. Not the same object
    as `ConversationState` — that's the cross-turn persistence layer; this is
    rebuilt fresh every `run_turn` call and discarded once the turn ends."""

    history: list[dict[str, str]]
    now: datetime
    consult_count: int
    consulted: list[str]
    verdicts: dict[str, Any]
    trace: list[dict[str, Any]]
    phase_hint: str | None
    qualifying_info_shared: bool
    slots_already_offered: bool
    offered_slots: list[dict[str, Any]]
    previously_offered_slots: list[dict[str, Any]]
    experience_shared_this_turn: bool
    sched_deferred_this_turn: bool
    next_step: str


def _route_node(state: TurnState) -> dict[str, Any]:
    if state["consult_count"] >= MAX_ADVISOR_CONSULTS:
        # Mirrors the legacy `while state.consult_count < MAX:` check being
        # false on entry: the loop body (routing call included) never runs.
        return {"next_step": "__guard__"}

    consultations_so_far = [
        {"advisor": name, "output": state["verdicts"][name].model_dump()}
        for name in state["consulted"]
    ]
    routing = main_agent.route(
        state["history"],
        consultations_so_far,
        state["phase_hint"],
        state["qualifying_info_shared"],
        state["slots_already_offered"],
    )

    experience_shared = state.get("experience_shared_this_turn", False) or bool(
        routing.candidate_shared_experience
    )
    sched_deferred = state.get("sched_deferred_this_turn", False)

    if sched_deferred and routing.next_step == "sched":
        return {
            "next_step": "__respond__",
            "experience_shared_this_turn": experience_shared,
        }

    if (
        routing.candidate_shared_experience
        and routing.next_step != "sched"
        and not state["qualifying_info_shared"]
        and not state["slots_already_offered"]
    ):
        sched_deferred = True

    return {
        "next_step": "__respond__" if routing.next_step == "respond" else routing.next_step,
        "experience_shared_this_turn": experience_shared,
        "sched_deferred_this_turn": sched_deferred,
    }


def _route_condition(state: TurnState) -> str:
    step = state.get("next_step", "")
    return "end" if step in ("__respond__", "__guard__") else step


def _advisor_condition(state: TurnState) -> str:
    return "end" if state.get("next_step") == "__respond__" else "loop"


def _exit_node(state: TurnState) -> dict[str, Any]:
    verdict = exit_advisor.decide(state["history"])
    trace_entry = {"advisor": "exit", "decision": verdict.decision, "reason": verdict.reason}
    return {
        "consult_count": state["consult_count"] + 1,
        "verdicts": {**state["verdicts"], "exit": verdict},
        "consulted": [*state["consulted"], "exit"],
        "trace": [*state["trace"], trace_entry],
        "next_step": "__respond__" if verdict.decision == "end" else "__loop__",
    }


def _sched_node(state: TurnState) -> dict[str, Any]:
    verdict = sched_advisor.decide(
        state["history"],
        now=state["now"],
        offered_slots=state["offered_slots"],
        previously_offered_slots=state["previously_offered_slots"],
    )
    new_slots = [slot.model_dump() for slot in verdict.proposed_slots]
    trace_entry = {
        "advisor": "sched",
        "decision": verdict.decision,
        "reason": verdict.reason,
        "slots": new_slots,
    }
    previously_offered = state["previously_offered_slots"]
    if verdict.decision == "sched" and new_slots:
        previously_offered = [*previously_offered, *new_slots]

    return {
        "consult_count": state["consult_count"] + 1,
        "verdicts": {**state["verdicts"], "sched": verdict},
        "consulted": [*state["consulted"], "sched"],
        "trace": [*state["trace"], trace_entry],
        "previously_offered_slots": previously_offered,
        "next_step": "__respond__" if verdict.decision in ("sched", "confirmed") else "__loop__",
    }


def _info_node(state: TurnState) -> dict[str, Any]:
    verdict = info_advisor.draft_answer(state["history"], top_k=3)
    trace_entry = {
        "advisor": "info",
        "decision": verdict.decision,
        "reason": verdict.reason,
        "sources": verdict.sources,
    }
    return {
        "consult_count": state["consult_count"] + 1,
        "verdicts": {**state["verdicts"], "info": verdict},
        "consulted": [*state["consulted"], "info"],
        "trace": [*state["trace"], trace_entry],
        "next_step": "__loop__",  # info is never conclusive by itself (matches legacy)
    }


def _build_graph() -> Any:
    builder = StateGraph(TurnState)
    builder.add_node("route", _route_node)
    builder.add_node("exit_advisor", _exit_node)
    builder.add_node("sched_advisor", _sched_node)
    builder.add_node("info_advisor", _info_node)

    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route",
        _route_condition,
        {"exit": "exit_advisor", "sched": "sched_advisor", "info": "info_advisor", "end": END},
    )
    for node_name in ("exit_advisor", "sched_advisor", "info_advisor"):
        builder.add_conditional_edges(node_name, _advisor_condition, {"end": END, "loop": "route"})

    return builder.compile()


_COMPILED_GRAPH = _build_graph()


def mermaid_diagram() -> str:
    """The graph's real structure as Mermaid source (`get_graph().draw_mermaid()`) —
    for presentation/documentation, generated from the actual compiled graph
    rather than hand-drawn."""
    return _COMPILED_GRAPH.get_graph().draw_mermaid()


def run_turn(
    user_message: str, state: ConversationState, *, now: datetime | None = None
) -> dict[str, Any]:
    """Same contract as `app.graph.run_turn` — see that module's docstring
    for the guard R-1 / `now` semantics, which are unchanged here."""

    resolved_now = now or get_settings().now()
    state.add_message("user", user_message)

    if _looks_meaningless(user_message):
        result = MainAgentOutput(
            action="continue",
            consulted=[],
            message="Sorry, I didn't quite catch that — could you say a bit more?",
            rationale="input too short/unclear to act on; skipped advisor consultation",
        ).model_dump()
        result["slots"] = []
        result["trace"] = []
        state.advisor_outputs.append(result)
        state.add_message("assistant", result["message"])
        return result

    last_action = _last_action(state)
    slots_already_offered = _slots_already_offered(state)
    offered_slots = _pending_offered_slots(state)
    phase_hint = "schedule" if _in_schedule_phase(state) else last_action

    initial_state: TurnState = {
        "history": state.history,
        "now": resolved_now,
        "consult_count": state.consult_count,
        "consulted": [],
        "verdicts": {},
        "trace": [],
        "phase_hint": phase_hint,
        "qualifying_info_shared": state.qualifying_info_shared,
        "slots_already_offered": slots_already_offered,
        "offered_slots": offered_slots,
        "previously_offered_slots": list(state.offered_slots_history),
        "experience_shared_this_turn": False,
        "sched_deferred_this_turn": False,
        "next_step": "",
    }

    final_state = _COMPILED_GRAPH.invoke(
        initial_state, config={"recursion_limit": _RECURSION_LIMIT}
    )

    if final_state.get("experience_shared_this_turn"):
        state.qualifying_info_shared = True
    state.offered_slots_history = final_state["previously_offered_slots"]

    consult_count = final_state["consult_count"]
    verdicts = final_state["verdicts"]
    consulted = final_state["consulted"]
    trace = final_state["trace"]

    if consult_count >= MAX_ADVISOR_CONSULTS and not verdicts:
        output = MainAgentOutput(
            action="continue",
            consulted=["guard"],
            message="I’m going to pause here and ask for a bit more context.",
            rationale="max advisor consultations reached (guard R-1)",
        )
        slots: list[dict[str, Any]] = []
    else:
        output, slots = _synthesize(consulted, verdicts, state, offered_slots)

    result = output.model_dump()
    result["slots"] = slots
    result["trace"] = trace
    state.advisor_outputs.append(result)
    state.add_message("assistant", result["message"])
    state.consult_count = 0
    return result
