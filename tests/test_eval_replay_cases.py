"""Tests for the eval replay harness's pure case-building logic (no API calls
— `_run_case`/`_replay_conversation_sequentially`/`main` in tests/eval_replay.py
hit the real API and are exercised manually, not here)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.eval_replay import (
    CONVERSATIONS_PATH,
    _build_cases,
    _is_divergence_artifact,
    _matches_any_offered_slot,
    _mentions_time,
    _mentions_weekday,
    _sequential_case_anchors,
)


def _load_conversations() -> list[dict]:
    return json.loads(Path(CONVERSATIONS_PATH).read_text(encoding="utf-8"))


def test_total_evaluable_cases_across_dataset() -> None:
    conversations = _load_conversations()
    total = sum(len(_build_cases(conversation)) for conversation in conversations)
    assert total == 44  # 59 labeled recruiter turns - 15 conversation openers


def test_conversation_opener_is_excluded() -> None:
    conversations = _load_conversations()
    first_conversation = conversations[0]
    cases = _build_cases(first_conversation)
    opener_turn_id = first_conversation["turns"][0]["turn_id"]
    assert all(case["turn_id"] != opener_turn_id for case in cases)


def test_known_case_shape_matches_conversation_one_turn_three() -> None:
    conversations = _load_conversations()
    conversation = next(c for c in conversations if c["conversation_id"] == 1)
    cases = _build_cases(conversation)

    case = next(c for c in cases if c["turn_id"] == 3)

    assert case["gold"] == "schedule"
    assert case["last_action"] == "continue"  # turn 1's gold label
    assert "five years" in case["trigger"]
    assert all(turn["turn_id"] != 3 for turn in case["history_prefix"])
    assert all(
        turn["turn_id"] < 2 for turn in case["history_prefix"]
    )  # trigger (turn 2) excluded too


def test_history_prefix_never_includes_trigger_or_labeled_turn() -> None:
    conversations = _load_conversations()
    for conversation in conversations:
        for case in _build_cases(conversation):
            prefix_ids = {turn["turn_id"] for turn in case["history_prefix"]}
            assert case["turn_id"] not in prefix_ids


# --- sequential mode (CORE-REV): _sequential_case_anchors -------------------


def test_sequential_total_evaluable_cases_matches_isolated_mode() -> None:
    """Both replay modes must be graded against the same 44 pairs so their
    accuracy numbers are directly comparable."""
    conversations = _load_conversations()
    total = sum(len(_sequential_case_anchors(conversation)) for conversation in conversations)
    assert total == 44


def test_sequential_anchor_shape_matches_conversation_one_turn_three() -> None:
    conversations = _load_conversations()
    conversation = next(c for c in conversations if c["conversation_id"] == 1)
    anchors = _sequential_case_anchors(conversation)

    anchor = next(a for a in anchors if a["turn_id"] == 3)

    assert anchor["gold"] == "schedule"
    assert "five years" in anchor["candidate_text"]
    # anchor points at the CANDIDATE turn's index (turn_id 2, 0-indexed as 1),
    # not the labeled recruiter turn's own index.
    assert conversation["turns"][anchor["turn_index"]]["turn_id"] == 2


def test_sequential_every_anchor_points_at_a_candidate_turn() -> None:
    conversations = _load_conversations()
    for conversation in conversations:
        for anchor in _sequential_case_anchors(conversation):
            assert conversation["turns"][anchor["turn_index"]]["speaker"] == "candidate"


def test_sequential_gold_matches_the_immediately_following_recruiter_turn() -> None:
    conversations = _load_conversations()
    for conversation in conversations:
        turns = conversation["turns"]
        for anchor in _sequential_case_anchors(conversation):
            next_turn = turns[anchor["turn_index"] + 1]
            assert next_turn["speaker"] == "recruiter"
            assert next_turn["turn_id"] == anchor["turn_id"]
            assert next_turn["label"] == anchor["gold"]


def test_sequential_anchor_carries_dataset_last_action() -> None:
    conversations = _load_conversations()
    conversation = next(c for c in conversations if c["conversation_id"] == 1)
    anchors = _sequential_case_anchors(conversation)

    anchor = next(a for a in anchors if a["turn_id"] == 3)

    assert anchor["dataset_last_action"] == "continue"  # turn 1's gold label


# --- divergence-artifact tagging (CORE-REV directive 1) ---------------------


def test_mentions_weekday_and_time() -> None:
    assert _mentions_weekday("Monday at 3 PM is good.") == "monday"
    assert _mentions_weekday("I have three years' experience.") is None
    assert _mentions_time("Tuesday at 10 AM works.") == "10am"
    assert _mentions_time("no time mentioned here") is None


def test_matches_any_offered_slot_by_weekday_or_time() -> None:
    offered = [{"schedule_id": 1, "date": "2024-04-17", "time": "10:00:00"}]  # a Wednesday
    assert _matches_any_offered_slot("Wednesday works", offered) is True
    assert _matches_any_offered_slot("10 AM works", offered) is True
    assert _matches_any_offered_slot("Monday at 3 PM is good.", offered) is False


def test_divergence_artifact_when_trajectory_already_diverged() -> None:
    """Our bot's last action differs from what the dataset's own script had
    at this point — the candidate's scripted reply is reacting to a
    conversation state our bot never actually reached."""
    assert (
        _is_divergence_artifact(
            "Sounds greate, see you then",
            our_last_action="continue",
            our_offered_slots=[],
            dataset_last_action="end",
        )
        is True
    )


def test_divergence_artifact_when_confirmation_does_not_match_our_offer() -> None:
    """Our bot DID offer real slots (matching the dataset's own last action),
    but the candidate's reply names a day our bot never actually offered —
    it was written to accept the dataset's fictional offer."""
    offered = [{"schedule_id": 1, "date": "2024-04-17", "time": "10:00:00"}]  # a Wednesday
    assert (
        _is_divergence_artifact(
            "Monday at 3 PM is good.",
            our_last_action="schedule",
            our_offered_slots=offered,
            dataset_last_action="schedule",
        )
        is True
    )


def test_not_divergence_when_trajectory_matches_and_offer_matches() -> None:
    offered = [{"schedule_id": 1, "date": "2024-04-17", "time": "10:00:00"}]  # a Wednesday
    assert (
        _is_divergence_artifact(
            "Wednesday at 10 AM works.",
            our_last_action="schedule",
            our_offered_slots=offered,
            dataset_last_action="schedule",
        )
        is False
    )


def test_divergence_artifact_uses_pending_offer_not_literal_last_action() -> None:
    """A restated offer (`graph._in_schedule_phase`'s `continue` follow-up,
    slots still pending) must still trigger the offer-mismatch check — not
    just a literal action=='schedule' turn."""
    offered = [{"schedule_id": 1, "date": "2024-04-17", "time": "10:00:00"}]  # a Wednesday
    assert (
        _is_divergence_artifact(
            "Monday at 3 PM is good.",
            our_last_action="continue",
            our_offered_slots=offered,
            dataset_last_action="continue",
        )
        is True
    )


def test_not_divergence_on_the_very_first_candidate_turn() -> None:
    """The first candidate turn always has our_last_action=None (our bot
    hasn't acted yet, since sequential replay never replays the dataset's
    own opener text) — this must NOT be auto-tagged as divergence just
    because the dataset's opener happened to carry some real gold label."""
    assert (
        _is_divergence_artifact(
            "I have three years' experience with Django and Flask.",
            our_last_action=None,
            our_offered_slots=[],
            dataset_last_action="continue",
        )
        is False
    )


def test_not_divergence_for_a_non_confirmation_message_with_matching_trajectory() -> None:
    """The over-eager-proactive-scheduling pattern (no day/time mentioned at
    all) must NOT be swept up as a divergence artifact — it's a genuine
    system behavior question, not a scripted-offer mismatch."""
    assert (
        _is_divergence_artifact(
            "I have three years' experience with Django and Flask.",
            our_last_action=None,
            our_offered_slots=[],
            dataset_last_action=None,
        )
        is False
    )
