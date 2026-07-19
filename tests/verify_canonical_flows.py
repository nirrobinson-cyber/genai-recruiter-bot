"""Canonical-flow verification (GRB-044, spec §4 Phase 4 "done when").

NOT a pytest test — makes real OpenAI calls (and hits the seeded DB / Chroma
index) for each of the four canonical flows required at the M2 gate. Run
manually:

    python -m tests.verify_canonical_flows

Each flow is a fresh conversation exercised against the real graph
(`app.graph.run_turn`), asserting the resulting action label and printing the
per-advisor trace (GRB-043) for a human to eyeball. Exits non-zero if any
flow's assertion fails.
"""

from __future__ import annotations

import sys

from app.config import get_settings
from app.graph import run_turn
from app.state import ConversationState

Flow = tuple[str, list[str], str]


def _print_trace(result: dict) -> None:
    print(f"  Bot [{result['action']}]: {result['message']}")
    for step in result["trace"]:
        print(f"    trace: {step['advisor']} -> {step['decision']} ({step['reason']})")


def _run_flow(name: str, messages: list[str], expected_final_action: str) -> bool:
    print(f"\n=== {name} ===")
    state = ConversationState()
    now = get_settings().now()
    result: dict = {}
    for message in messages:
        print(f"You: {message}")
        result = run_turn(message, state, now=now)
        _print_trace(result)

    passed = result.get("action") == expected_final_action
    status = "PASS" if passed else "FAIL"
    print(
        f"--- {status}: expected final action '{expected_final_action}', got '{result.get('action')}' ---"
    )
    return passed


def main() -> int:
    flows: list[Flow] = [
        (
            "Q&A flow (Info Advisor)",
            ["What kind of Python stack does this role use — Django, Flask, or something else?"],
            "continue",
        ),
        (
            "Scheduling flow, incl. relative date (Sched Advisor)",
            ["How about next Friday for an interview?"],
            "schedule",
        ),
        (
            "Refusal -> end (Exit Advisor)",
            ["I'm sorry, but I'm no longer interested."],
            "end",
        ),
        (
            "Opt-out -> end (Exit Advisor)",
            ["Please remove me from your list. Thanks."],
            "end",
        ),
    ]

    results = [_run_flow(name, messages, expected) for name, messages, expected in flows]

    print(f"\n{sum(results)}/{len(results)} canonical flows passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
