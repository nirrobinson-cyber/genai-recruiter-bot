"""Eval replay harness (Epic E5, GRB-050/051; CORE-REV methodology fix, spec §9).

NOT a pytest test — makes real OpenAI calls for every evaluated turn across
all 15 labeled conversations in data/raw/sms_conversations.json. Run manually:

    python -m tests.eval_replay                 # sequential (default)
    python -m tests.eval_replay --mode isolated  # old per-turn-isolated mode
    python -m tests.eval_replay --mode both      # run + report both

Two replay modes, both graded against the same 44 (candidate-turn, gold)
pairs:

- "sequential" (default, matches spec §9's "feed the system the history up
  to that point" literally): ONE ConversationState per conversation, walked
  turn-by-turn in order through the real graph. State — offered slots,
  booking status, the proactive-escalation flag — accumulates naturally,
  exactly as it would in a live conversation. The candidate's turns come
  from the dataset (ground truth of what a real candidate said); the
  "recruiter" side is our own bot's real generated replies, not the
  dataset's static text — because the point is to test whether *our*
  system's own accumulated state tracks the conversation correctly as it
  matures via its own decisions.
- "isolated" (the original design, kept for comparison): each labeled turn
  gets a FRESH ConversationState seeded only with the dataset's own static
  prefix text and a bare `{"action": last_gold_action}` marker — no real
  slot data. This under-measures anything depending on real state (e.g. a
  confirmed-booking turn can never resolve, since `offered_slots` is always
  empty) — see CLAUDE.md's 2026-07-19 CORE-REV entry.
"""

from __future__ import annotations

import argparse
import calendar
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app import graph
from app.graph import run_turn
from app.state import ConversationState

CONVERSATIONS_PATH = Path("data/raw/sms_conversations.json")

_WEEKDAY_NAMES = {name.lower() for name in calendar.day_name}
_TIME_PATTERN = re.compile(r"\b(\d{1,2})\s*(am|pm)\b", re.IGNORECASE)


def _role(speaker: str) -> str:
    return "user" if speaker == "candidate" else "assistant"


# --- isolated mode (original design, kept behind --mode isolated) ----------


def _build_cases(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    """One case per labeled recruiter turn that has a preceding candidate turn."""

    turns = conversation["turns"]
    now = datetime.fromisoformat(conversation["start_time_utc"].replace("Z", "+00:00"))
    cases: list[dict[str, Any]] = []
    last_gold_action: str | None = None

    for index, turn in enumerate(turns):
        if turn["speaker"] != "recruiter":
            continue
        if index > 0:
            cases.append(
                {
                    "conversation_id": conversation["conversation_id"],
                    "turn_id": turn["turn_id"],
                    "history_prefix": turns[: index - 1],
                    "trigger": turns[index - 1]["text"],
                    "gold": turn["label"],
                    "now": now,
                    "last_action": last_gold_action,
                }
            )
        last_gold_action = turn["label"]

    return cases


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Replay one case through the real graph; returns the full `run_turn`
    result (action, message, consulted, trace, slots) — callers that only
    need the predicted label can read `result["action"]`."""
    state = ConversationState()
    for turn in case["history_prefix"]:
        state.add_message(_role(turn["speaker"]), turn["text"])
    if case["last_action"] is not None:
        state.advisor_outputs.append({"action": case["last_action"]})

    return run_turn(case["trigger"], state, now=case["now"])


def _replay_isolated(conversations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for conversation in conversations:
        for case in _build_cases(conversation):
            result = _run_case(case)
            results.append(
                {
                    "conversation_id": case["conversation_id"],
                    "turn_id": case["turn_id"],
                    "trigger": case["trigger"],
                    "gold": case["gold"],
                    "predicted": result["action"],
                    "trace": result["trace"],
                    # Isolated mode always seeds `our_last_action ==
                    # dataset_last_action` by construction, and never has
                    # real offered slots — the divergence concept doesn't
                    # apply to it (it's a different failure mode entirely).
                    "divergence_artifact": False,
                }
            )
    return results


# --- sequential mode (default) ---------------------------------------------


def _sequential_case_anchors(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure pairing logic, no LLM/API calls: for each candidate turn, the
    immediately following labeled recruiter turn it should be graded
    against (if any) — i.e. what a real recruiter actually did next, which
    is what our own turn's predicted action is compared to. Also carries
    `dataset_last_action` — the *original* recruiter's own gold action right
    before this candidate turn — used by `_is_divergence_artifact` to detect
    when our bot's own trajectory has already drifted from the dataset's
    script by this point."""

    turns = conversation["turns"]
    anchors: list[dict[str, Any]] = []
    last_gold_action: str | None = None
    for index, turn in enumerate(turns):
        if turn["speaker"] == "recruiter":
            last_gold_action = turn["label"]
            continue
        next_turn = turns[index + 1] if index + 1 < len(turns) else None
        if (
            next_turn is not None
            and next_turn["speaker"] == "recruiter"
            and next_turn.get("label") is not None
        ):
            anchors.append(
                {
                    "conversation_id": conversation["conversation_id"],
                    "turn_index": index,
                    "candidate_text": turn["text"],
                    "gold": next_turn["label"],
                    "turn_id": next_turn["turn_id"],
                    "dataset_last_action": last_gold_action,
                }
            )
    return anchors


def _mentions_weekday(text: str) -> str | None:
    lowered = text.lower()
    for name in _WEEKDAY_NAMES:
        if name in lowered:
            return name
    return None


def _mentions_time(text: str) -> str | None:
    match = _TIME_PATTERN.search(text)
    if not match:
        return None
    hour, meridiem = match.groups()
    return f"{hour}{meridiem.lower()}"


def _looks_like_confirmation_attempt(text: str) -> bool:
    return _mentions_weekday(text) is not None or _mentions_time(text) is not None


def _slot_weekday(slot: dict[str, Any]) -> str:
    return calendar.day_name[date.fromisoformat(slot["date"]).weekday()].lower()


def _slot_time_label(slot: dict[str, Any]) -> str:
    hour = int(slot["time"].split(":")[0])
    meridiem = "am" if hour < 12 else "pm"
    hour12 = hour % 12 or 12
    return f"{hour12}{meridiem}"


def _matches_any_offered_slot(text: str, offered_slots: list[dict[str, Any]]) -> bool:
    weekday = _mentions_weekday(text)
    time_label = _mentions_time(text)
    for slot in offered_slots:
        if weekday is not None and _slot_weekday(slot) == weekday:
            return True
        if time_label is not None and _slot_time_label(slot) == time_label:
            return True
    return False


def _is_divergence_artifact(
    trigger: str,
    our_last_action: str | None,
    our_offered_slots: list[dict[str, Any]],
    dataset_last_action: str | None,
) -> bool:
    """A miss caused by our bot's own conversation having already diverged
    from the dataset's script — the candidate's (real, dataset-scripted)
    reply reacts to an offer/state our bot didn't actually produce, not a
    fresh reasoning error at this turn. Two ways this shows up:

    (a) our bot's own trajectory had already produced a *different* action
        than the dataset's script by this point (e.g. the dataset expected
        a booking to already be confirmed, ours never offered anything), or
    (b) our bot DOES have a pending offer (real slots — possibly restated
        via a `continue` follow-up, not just the literal `schedule` turn
        itself; see `graph._pending_offered_slots`), but the candidate's
        reply names a day/time that matches none of them (it was written to
        accept the *dataset's* fictional offer, not our DB-verified one).

    This is a documented heuristic, not ground truth — see CLAUDE.md's
    2026-07-19 CORE-REV entry for the methodology note.

    `our_last_action is None` (the very first candidate turn — our bot
    hasn't acted yet, since sequential replay never re-plays the dataset's
    own opener text) is NOT itself a divergence signal: comparing "no prior
    action at all" against whatever label the dataset's opener happened to
    carry is spurious and would mistag every first-turn error."""

    if our_last_action is not None and our_last_action != dataset_last_action:
        return True
    return (
        bool(our_offered_slots)
        and _looks_like_confirmation_attempt(trigger)
        and not _matches_any_offered_slot(trigger, our_offered_slots)
    )


def _replay_conversation_sequentially(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    anchors_by_index = {
        anchor["turn_index"]: anchor for anchor in _sequential_case_anchors(conversation)
    }
    now = datetime.fromisoformat(conversation["start_time_utc"].replace("Z", "+00:00"))
    state = ConversationState()
    results: list[dict[str, Any]] = []

    for index, turn in enumerate(conversation["turns"]):
        if turn["speaker"] != "candidate":
            continue
        anchor = anchors_by_index.get(index)
        our_last_action = graph._last_action(state)
        our_offered_slots = graph._pending_offered_slots(state)
        result = run_turn(turn["text"], state, now=now)
        if anchor is not None:
            results.append(
                {
                    "conversation_id": anchor["conversation_id"],
                    "turn_id": anchor["turn_id"],
                    "trigger": anchor["candidate_text"],
                    "gold": anchor["gold"],
                    "predicted": result["action"],
                    "trace": result["trace"],
                    "divergence_artifact": _is_divergence_artifact(
                        anchor["candidate_text"],
                        our_last_action,
                        our_offered_slots,
                        anchor["dataset_last_action"],
                    ),
                }
            )
    return results


def _replay_sequential(conversations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        result
        for conversation in conversations
        for result in _replay_conversation_sequentially(conversation)
    ]


# --- shared summary ----------------------------------------------------------


def _accuracy_table(results: list[dict[str, Any]]) -> tuple[int, dict[str, list[int]]]:
    per_class: dict[str, list[int]] = {"continue": [0, 0], "schedule": [0, 0], "end": [0, 0]}
    correct = 0
    for result in results:
        gold = result["gold"]
        per_class[gold][1] += 1
        if result["predicted"] == gold:
            correct += 1
            per_class[gold][0] += 1
    return correct, per_class


def _print_accuracy(label: str, results: list[dict[str, Any]]) -> None:
    correct, per_class = _accuracy_table(results)
    total = len(results)
    rate = f"{correct / total:.1%}" if total else "n/a"
    print(f"{label}: {correct}/{total} ({rate})")
    for cls, (cls_correct, cls_total) in per_class.items():
        cls_rate = f"{cls_correct / cls_total:.1%}" if cls_total else "n/a"
        print(f"  {cls}: {cls_correct}/{cls_total} ({cls_rate})")


def _print_summary(mode: str, results: list[dict[str, Any]]) -> None:
    print(f"\n=== mode: {mode} ===")
    _print_accuracy("Raw accuracy (all misses count)", results)

    if any(result["divergence_artifact"] for result in results):
        genuine_only = [
            result
            for result in results
            if result["gold"] == result["predicted"] or not result["divergence_artifact"]
        ]
        n_divergence = sum(
            1
            for result in results
            if result["divergence_artifact"] and result["gold"] != result["predicted"]
        )
        print(
            f"\nAdjusted accuracy (excluding {n_divergence} divergence-artifact misses — see CLAUDE.md 2026-07-19 "
            "CORE-REV methodology note):"
        )
        _print_accuracy("Adjusted", genuine_only)

    misses = [result for result in results if result["gold"] != result["predicted"]]
    print(f"\nMisclassified turns ({len(misses)}):")
    for miss in misses:
        tag = "DIVERGENCE" if miss["divergence_artifact"] else "GENUINE"
        print(
            f"- [{tag}] conversation {miss['conversation_id']} turn {miss['turn_id']}: gold={miss['gold']} predicted={miss['predicted']}"
        )
        print(f"  trigger: {miss['trigger']!r}")
        for step in miss["trace"]:
            print(f"    trace: {step['advisor']} -> {step['decision']} ({step['reason']})")


def main(mode: str = "sequential") -> None:
    conversations = json.loads(CONVERSATIONS_PATH.read_text(encoding="utf-8"))

    if mode in ("sequential", "both"):
        _print_summary("sequential", _replay_sequential(conversations))
    if mode in ("isolated", "both"):
        _print_summary("isolated", _replay_isolated(conversations))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["sequential", "isolated", "both"], default="sequential")
    main(parser.parse_args().mode)
