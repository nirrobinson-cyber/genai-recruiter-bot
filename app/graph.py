"""Turn graph (spec §12, §4).

Plain-Python control flow (not the `langgraph` library) implementing the
flowchart's behavior: the Main Agent's own routing decision (`main_agent.route`,
spec §5.1) picks which advisor to consult next, or "respond" to stop and
synthesize a reply — looping up to `MAX_ADVISOR_CONSULTS` times per turn
(guard R-1). Each advisor's decision is a genuine LLM call
(Exit/Sched/Info, GRB-021/023/024); the final output only claims an action
(`end`/`schedule`) that an advisor actually decided this turn.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.config import get_settings
from app.modules.exit_advisor import advisor as exit_advisor
from app.modules.info_advisor import advisor as info_advisor
from app.modules.main_agent import agent as main_agent
from app.modules.sched_advisor import advisor as sched_advisor
from app.schemas import MainAgentOutput, SlotProposal
from app.state import ConversationState

MAX_ADVISOR_CONSULTS = 3

# Short replies that ARE meaningful despite their length (a slot count, a
# plain yes/no) must not be swept up by the "meaningless input" guard below.
_SHORT_MEANINGFUL_REPLIES = {"ok", "no", "yes", "hi", "y", "n"}
_MEANINGLESS_MIN_LENGTH = 3


def _looks_meaningless(message: str) -> bool:
    """A stray keystroke ("f", "x") or empty input — not an actual attempt to
    communicate. Distinct from a short-but-real reply (a bare "5" answering
    "years of experience?", "ok", "yes"), which must still reach an advisor."""
    stripped = message.strip()
    if not stripped:
        return True
    if stripped.isdigit() or stripped.lower() in _SHORT_MEANINGFUL_REPLIES:
        return False
    return len(stripped) < _MEANINGLESS_MIN_LENGTH


def _already_answered_info(state: ConversationState) -> bool:
    return any(entry.get("consulted") == ["info"] for entry in state.advisor_outputs)


def _last_action(state: ConversationState) -> str | None:
    return state.advisor_outputs[-1]["action"] if state.advisor_outputs else None


def _slots_already_offered(state: ConversationState) -> bool:
    return any(entry.get("action") == "schedule" for entry in state.advisor_outputs)


def _in_schedule_phase(state: ConversationState) -> bool:
    """True while an offer is still open: a `schedule` action started it and
    no `end` (booking or exit) has closed it since. Any number of `continue`
    replies in between (asking "when", an unparseable date, an info detour)
    must not silently drop that open-offer context (bug: a 3rd follow-up
    after an offer lost track of it entirely and got a generic reply)."""
    for entry in reversed(state.advisor_outputs):
        if entry.get("action") == "end":
            return False
        if entry.get("action") == "schedule":
            return True
    return False


def _pending_offered_slots(state: ConversationState) -> list[dict[str, Any]]:
    """The slots from the most recent still-open offer (see `_in_schedule_phase`)."""
    for entry in reversed(state.advisor_outputs):
        if entry.get("action") == "end":
            return []
        if entry.get("action") == "schedule":
            return entry.get("slots", [])
    return []


def _format_slots(slots: list[Any]) -> str:
    return "; ".join(f"{slot.date} at {slot.time}" for slot in slots)


def _synthesize(
    consulted: list[str],
    verdicts: dict[str, Any],
    state: ConversationState,
    offered_slots: list[dict[str, Any]],
) -> tuple[MainAgentOutput, list[dict[str, Any]]]:
    """Build the final MainAgentOutput from whichever advisor(s) ran this turn."""

    if "exit" in verdicts and verdicts["exit"].decision == "end":
        return (
            MainAgentOutput(
                action="end",
                consulted=consulted,
                message="Thanks for your time. I’ll stop here.",
                rationale=verdicts["exit"].reason,
            ),
            [],
        )

    if "sched" in verdicts and verdicts["sched"].decision == "confirmed":
        slot = verdicts["sched"].proposed_slots[0]
        message = f"Great, you're all set! Your interview is confirmed for {slot.date} at {slot.time}. You'll receive a calendar invite shortly."
        return MainAgentOutput(
            action="end", consulted=consulted, message=message, rationale=verdicts["sched"].reason
        ), []

    if "sched" in verdicts and verdicts["sched"].decision == "sched":
        proposed = verdicts["sched"].proposed_slots
        slots = [slot.model_dump() for slot in proposed]
        if proposed:
            message = f"I can offer these interview times: {_format_slots(proposed)}. Which works best for you?"
        else:
            message = (
                "I don't have any further open interview times to offer right now — "
                "I'll have the recruiter follow up with you directly to find a time that works."
            )
        return (
            MainAgentOutput(
                action="schedule",
                consulted=consulted,
                message=message,
                rationale=verdicts["sched"].reason,
            ),
            slots,
        )

    # A slot offer just happened: a declined/unresolved sched verdict this
    # turn is still more relevant than an unrelated info decline (the bug:
    # "april 2024?" after an offer used to fall through to a generic info
    # fallback instead of asking which date/day the candidate meant). If real
    # slots were already offered, restate THOSE dates instead of a generic
    # question — the candidate shouldn't have to guess what's on offer when
    # we already told them (bug: "when" got a vague re-ask instead of the
    # actual dates already retrieved from the DB).
    if _in_schedule_phase(state) and "sched" in verdicts:
        if offered_slots:
            proposed = [SlotProposal(**slot) for slot in offered_slots]
            message = f"Here are the times I have available: {_format_slots(proposed)}. Which one works, or let me know another day?"
        else:
            message = "Could you tell me which day or date works best for the interview?"
        return (
            MainAgentOutput(
                action="continue",
                consulted=consulted,
                message=message,
                rationale=verdicts["sched"].reason,
            ),
            offered_slots,
        )

    if "info" in verdicts and verdicts["info"].draft_answer:
        verdict = verdicts["info"]
        follow_up = (
            " We’ve already discussed the role; what else would you like to know?"
            if _already_answered_info(state)
            else ""
        )
        message = (verdict.draft_answer + follow_up).strip()
        return MainAgentOutput(
            action="continue", consulted=consulted, message=message, rationale=verdict.reason
        ), []

    if "exit" in verdicts:
        return (
            MainAgentOutput(
                action="continue",
                consulted=consulted,
                message="No worries — happy to keep going. What would you like to know?",
                rationale=verdicts["exit"].reason,
            ),
            [],
        )

    if "sched" in verdicts:
        return (
            MainAgentOutput(
                action="continue",
                consulted=consulted,
                message="Let me know when you'd like to schedule and I can check availability.",
                rationale=verdicts["sched"].reason,
            ),
            [],
        )

    if "info" in verdicts:
        return (
            MainAgentOutput(
                action="continue",
                consulted=consulted,
                message="Could you tell me more about what you'd like to know?",
                rationale=verdicts["info"].reason,
            ),
            [],
        )

    return (
        MainAgentOutput(
            action="continue",
            consulted=consulted,
            message="Could you tell me more about what you're looking for?",
            rationale="no advisor consultation needed this turn",
        ),
        [],
    )


def run_turn(
    user_message: str, state: ConversationState, *, now: datetime | None = None
) -> dict[str, Any]:
    """Process one user turn and return the main-agent output.

    `state.consult_count` counts advisor consultations *within this turn*
    (guard R-1: max 3 per turn, not per conversation) — it is reset once the
    turn is done so it never carries over and starves later turns.

    `now` overrides `settings.now()` for this turn's date resolution — used
    by the eval replay harness to resolve dates against each conversation's
    own `start_time_utc` instead of the wall clock/demo override (spec §9,
    A-5). Defaults to `settings.now()` for normal terminal/Streamlit use.
    """

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

    consulted: list[str] = []
    verdicts: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    last_action = _last_action(state)
    slots_already_offered = _slots_already_offered(state)
    offered_slots = _pending_offered_slots(state)
    # Feed the LLM router a synthesized "schedule" phase hint for as long as
    # an offer is still open, not just literally the previous turn's action —
    # otherwise the very first `continue` reply after an offer (e.g. "when")
    # already erases the "treat date-like replies as scheduling" cue for any
    # further follow-up in the same open thread.
    phase_hint = "schedule" if _in_schedule_phase(state) else last_action
    # Deliberately NOT applied to `state.qualifying_info_shared` until after
    # the loop: the maturity rule requires qualifying info to have been
    # shared on an EARLIER turn before proactively escalating (see
    # main_agent's prompt) — if a same-turn re-consult saw the flag flip
    # mid-loop, escalation could fire in the very same turn the info was
    # first mentioned, defeating that rule entirely.
    experience_shared_this_turn = False

    while state.consult_count < MAX_ADVISOR_CONSULTS:
        consultations_so_far = [
            {"advisor": name, "output": verdicts[name].model_dump()} for name in consulted
        ]
        routing = main_agent.route(
            state.history,
            consultations_so_far,
            phase_hint,
            state.qualifying_info_shared,
            slots_already_offered,
        )
        if routing.candidate_shared_experience:
            experience_shared_this_turn = True
        if routing.next_step == "respond":
            break

        state.consult_count += 1
        advisor_name = routing.next_step
        consulted.append(advisor_name)

        if advisor_name == "exit":
            verdicts["exit"] = exit_advisor.decide(state.history)
            trace.append(
                {
                    "advisor": "exit",
                    "decision": verdicts["exit"].decision,
                    "reason": verdicts["exit"].reason,
                }
            )
            if verdicts["exit"].decision == "end":
                break
        elif advisor_name == "sched":
            verdicts["sched"] = sched_advisor.decide(
                state.history,
                now=resolved_now,
                offered_slots=offered_slots,
                previously_offered_slots=state.offered_slots_history,
            )
            new_slots = [slot.model_dump() for slot in verdicts["sched"].proposed_slots]
            trace.append(
                {
                    "advisor": "sched",
                    "decision": verdicts["sched"].decision,
                    "reason": verdicts["sched"].reason,
                    "slots": new_slots,
                }
            )
            if verdicts["sched"].decision == "sched" and new_slots:
                state.offered_slots_history.extend(new_slots)
            if verdicts["sched"].decision in ("sched", "confirmed"):
                break
        else:
            verdicts["info"] = info_advisor.draft_answer(state.history, top_k=3)
            trace.append(
                {
                    "advisor": "info",
                    "decision": verdicts["info"].decision,
                    "reason": verdicts["info"].reason,
                    "sources": verdicts["info"].sources,
                }
            )

    if experience_shared_this_turn:
        state.qualifying_info_shared = True

    if state.consult_count >= MAX_ADVISOR_CONSULTS and not verdicts:
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
