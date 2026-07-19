"""Sched Advisor (spec §5.3) — decides sched / dont_sched / confirmed.

The LLM never supplies verified slots itself (it has no DB access); once it
decides "sched", this module resolves the relative date from the candidate's
latest message and looks up real, DB-verified slots in the same turn (hard
constraint S-3), overwriting anything the model guessed. "confirmed" is a
separate booking-completion path: once slots were offered, if the candidate
accepts one of *those specific* slots, this module books it via the existing
`tools.book_slot` and reports the confirmed slot — never trusting the model's
own pointer without checking it against what was actually offered.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from app.config import get_settings
from app.llm_client import cached_parse, history_to_messages
from app.modules.sched_advisor.date_resolver import default_forward_window, resolve_relative_date
from app.modules.sched_advisor.tools import book_slot, get_available_slots
from app.schemas import SchedAdvisorOutput, SlotProposal
from app.structured_output import get_structured_output

POSITION = "Python Dev"  # only position in scope for this PoC (spec §2.3)

# Distinguishes "no date was named at all" (default to nearest available
# slots) from "a date was attempted but is garbled/unresolvable" (still
# decline and ask to clarify — never silently guess a specific wrong date,
# see date_resolver's own anti-guessing note). Digits are only a date-attempt
# signal in a date-SHAPED context (a time like "10am", a numeric date like
# "14/4/24", an ordinal "14th") — a bare `\d` used to match ANY digit,
# wrongly flagging "3 years' experience"/"5 years of experience" as a
# garbled date attempt (blocking the proactive-offer fallback below) while
# spelled-out "five years" worked fine.
_DATE_ATTEMPT_HINTS = re.compile(
    r"\d{1,2}\s*(am|pm)\b|"
    r"\d{1,2}[/.]\d{1,2}[/.]\d{2,4}|"
    r"\d{1,2}(st|nd|rd|th)\b|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"tomorrow|today|next|week|month|"
    r"january|february|march|april|may|june|july|august|september|october|november|december",
    re.IGNORECASE,
)


def _looks_like_a_date_attempt(message: str) -> bool:
    return bool(_DATE_ATTEMPT_HINTS.search(message))


BASE_PROMPT = """You are the Scheduling Advisor for a recruiting SMS chatbot hiring for \
a Python Developer role. Given the complete chat history, decide whether now is the right \
moment to propose interview times ("sched") or not ("dont_sched").

You do NOT have access to the interview calendar — always leave proposed_slots empty; a \
separate system component looks up real, verified slots after your decision.

This recruiting flow always proposes interview times once the candidate has shared \
relevant qualifying background (years of experience, skills, past projects) — don't wait \
for an explicit "let's schedule" ask; sharing that background IS the cue to schedule.

Similarly, if the candidate says a previously proposed time doesn't work for them (busy, \
unavailable, "those slots don't work") without expressing general disinterest in the role, \
that is still "sched" — propose new/alternative times, don't give up on scheduling.

Examples:

History: candidate says "Sure, when can we set up an interview?"
Decision: sched (reason: candidate explicitly asked to schedule).

History: candidate says "Can you tell me more about the tech stack first?"
Decision: dont_sched (reason: candidate is still gathering information, not ready to schedule).

History: candidate says "Monday at 3 PM works for me." (no slots offered yet this conversation)
Decision: sched (reason: candidate proposed/accepted a concrete time).

History: candidate says "I've been using Python professionally for five years, mostly for \
data analysis." (no slots offered yet this conversation)
Decision: sched (reason: candidate shared qualifying experience — time to proactively offer \
interview times, not just acknowledge and wait).

History: candidate says "I can't at that time — I'm busy." (a time was offered earlier this \
conversation; candidate hasn't said they're no longer interested)
Decision: sched (reason: candidate declined a specific offered time, not scheduling itself — \
propose alternative times).
"""

CONFIRMATION_PROMPT_ADDENDUM = """
Interview slots were already offered to the candidate this conversation (listed below). \
If the candidate's latest message is accepting ONE of *those specific* slots (matching by \
day and/or time), return decision="confirmed" with confirmed_schedule_id set to that \
slot's id from the list below.

If instead the candidate names a CONCRETE day/date/time that does NOT match any offered \
slot (a specific weekday, a numeric date like "14/4/24", a month/day, an explicit time), \
that is still decision="sched" — they're proposing a different time and we should look up \
availability for THAT date, not decline.

If the candidate REJECTS the offered batch outright without naming a new date ("none", \
"none of those", "those don't work", "other dates", "do you have anything else"), that is \
ALSO decision="sched" — they still want to schedule, just not these specific times, so look \
up different (later) availability. Only use "dont_sched" for a genuinely vague/unclear reply \
that neither rejects the offer nor names any day or date at all (e.g. "when", "not sure", \
"let me check").

Examples:
History: candidate says "Monday at 3 PM is good."
Offered slots include one on Monday at 3 PM.
Decision: confirmed, confirmed_schedule_id=<that slot's id> (reason: candidate accepted the offered slot).

History: candidate says "14/4/24"
Offered slots are all later in April, none on the 14th.
Decision: sched (reason: candidate proposed a different concrete date; look up availability for it).

History: candidate says "None of those work for me."
Decision: sched (reason: candidate rejected the offered batch; look up different, later availability).

History: candidate says "when"
Decision: dont_sched (reason: no concrete day/date given — this is a request for the offer, not a new date).
"""

FALLBACK = SchedAdvisorOutput(
    decision="dont_sched",
    proposed_slots=[],
    reason="LLM call failed after retry; defaulting to not scheduling",
)


def _call_llm(history: list[dict[str, str]], offered_slots: list[dict]) -> SchedAdvisorOutput:
    settings = get_settings()
    system_prompt = BASE_PROMPT
    messages = history_to_messages(system_prompt, history)
    if offered_slots:
        slots_block = "\n".join(
            f"- id={slot['schedule_id']}: {slot['date']} {slot['time']}" for slot in offered_slots
        )
        messages.append(
            {
                "role": "system",
                "content": CONFIRMATION_PROMPT_ADDENDUM + f"\nOffered slots:\n{slots_block}",
            }
        )

    return cached_parse(
        model=settings.advisor_model,
        temperature=settings.decision_temperature,
        messages=messages,
        response_format=SchedAdvisorOutput,
    )


def _latest_user_message(history: list[dict[str, str]]) -> str:
    for turn in reversed(history):
        if turn["role"] == "user":
            return turn["content"]
    return ""


def _confirm_booking(verdict: SchedAdvisorOutput, offered_slots: list[dict]) -> SchedAdvisorOutput:
    matched = next(
        (slot for slot in offered_slots if slot["schedule_id"] == verdict.confirmed_schedule_id),
        None,
    )
    if matched is None:
        return SchedAdvisorOutput(
            decision="dont_sched",
            proposed_slots=[],
            reason="candidate's confirmation didn't clearly match an offered slot; ask them to confirm which one",
        )

    booking = book_slot.invoke({"schedule_id": matched["schedule_id"]})
    if not booking["booked"]:
        return SchedAdvisorOutput(
            decision="dont_sched",
            proposed_slots=[],
            reason="that slot is no longer available; ask the candidate to pick another",
        )

    return SchedAdvisorOutput(
        decision="confirmed",
        proposed_slots=[SlotProposal(**matched)],
        confirmed_schedule_id=matched["schedule_id"],
        reason=verdict.reason,
    )


def decide(
    history: list[dict[str, str]],
    now: datetime,
    offered_slots: list[dict] | None = None,
    previously_offered_slots: list[dict] | None = None,
) -> SchedAdvisorOutput:
    """Decide sched/dont_sched/confirmed from the complete chat history (rule R-2, N-3).

    `offered_slots` is the CURRENT pending batch (for confirmation-matching,
    day/time against a specific offer). `previously_offered_slots` is every
    slot ever offered this conversation, across ALL batches — used so a
    rejection ("none", "other dates") never re-offers something already
    shown, and the "no date named" fallback advances past the latest
    previously-offered date instead of always restarting from `now` (the
    reported bug: rejecting an offer with no new date kept re-surfacing the
    very first, earliest slots)."""

    offered_slots = offered_slots or []
    previously_offered_slots = previously_offered_slots or []
    verdict = get_structured_output(lambda: _call_llm(history, offered_slots), fallback=FALLBACK)

    if verdict.decision == "confirmed":
        return _confirm_booking(verdict, offered_slots)

    if verdict.decision != "sched":
        return verdict

    excluded_ids = {slot["schedule_id"] for slot in previously_offered_slots}
    already_offered_dates = [date.fromisoformat(slot["date"]) for slot in previously_offered_slots]
    floor_date = max(already_offered_dates) if already_offered_dates else None

    latest_message = _latest_user_message(history)
    date_range = resolve_relative_date(latest_message, now)
    if date_range is None:
        if _looks_like_a_date_attempt(latest_message):
            return SchedAdvisorOutput(
                decision="dont_sched",
                proposed_slots=[],
                reason="candidate's requested date wasn't clear enough to look up slots; ask them to clarify",
            )
        # No date was named at all (e.g. shared qualifying background, or
        # rejected the offered times without proposing a new one) —
        # proactively offer the nearest available slots instead of asking an
        # open-ended "when works?" question. Advance past whatever's already
        # been offered so a rejection doesn't loop back to the same slots.
        date_range = default_forward_window(now, after=floor_date)

    raw_slots = get_available_slots.invoke(
        {
            "position": POSITION,
            "from_date": date_range.from_date.isoformat(),
            "to_date": date_range.to_date.isoformat(),
            "limit": 3 + len(excluded_ids),
        }
    )
    candidates = [slot for slot in raw_slots if slot["schedule_id"] not in excluded_ids]
    proposed_slots = [
        SlotProposal(schedule_id=slot["schedule_id"], date=slot["date"], time=slot["time"])
        for slot in candidates[:3]
    ]
    if not proposed_slots:
        return SchedAdvisorOutput(
            decision="sched",
            proposed_slots=[],
            reason="no further open slots in that window after excluding previously offered times",
        )
    return SchedAdvisorOutput(
        decision="sched", proposed_slots=proposed_slots, reason=verdict.reason
    )
