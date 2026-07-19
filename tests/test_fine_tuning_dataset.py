"""Tests for the Exit Advisor fine-tuning dataset builder (GRB-030, GRB-031).

No real API calls — pure data transformation, exercised against a small
in-memory fixture plus one sanity check against the real dataset file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.modules.fine_tuning import dataset_builder as db


def _make_conversation(conversation_id: int) -> dict[str, Any]:
    """4-turn conversation: opener (skipped, no history), a `schedule`
    decision, and an `end` decision — every conversation carries one `end`
    example, mirroring the real dataset's structure."""

    return {
        "conversation_id": conversation_id,
        "turns": [
            {"speaker": "recruiter", "text": "Hi, thanks for applying!", "label": "continue"},
            {"speaker": "candidate", "text": "Happy to chat.", "label": None},
            {"speaker": "recruiter", "text": "How about Tuesday at 10 AM?", "label": "schedule"},
            {"speaker": "candidate", "text": "Actually I took another job.", "label": None},
            {"speaker": "recruiter", "text": "Understood, good luck!", "label": "end"},
        ],
    }


FIXTURE_CONVERSATIONS = [_make_conversation(i) for i in range(1, 6)]  # ids 1..5


def _target_decision(example: dict[str, Any]) -> str:
    return json.loads(example["messages"][-1]["content"])["decision"]


def test_label_mapping() -> None:
    # Each fixture conversation contributes exactly two examples, in turn
    # order: the `schedule` turn (-> dont_end) then the `end` turn (-> end).
    examples = db.build_examples(FIXTURE_CONVERSATIONS)
    assert len(examples) == 2 * len(FIXTURE_CONVERSATIONS)
    assert all(_target_decision(e) == "dont_end" for e in examples[0::2])
    assert all(_target_decision(e) == "end" for e in examples[1::2])


def test_split_has_no_conversation_overlap() -> None:
    train_ids, val_ids = db.split_conversation_ids(FIXTURE_CONVERSATIONS, val_fraction=0.2, seed=42)
    assert set(train_ids).isdisjoint(set(val_ids))
    assert set(train_ids) | set(val_ids) == {c["conversation_id"] for c in FIXTURE_CONVERSATIONS}


def test_build_dataset_splits_are_nonempty_and_stratified(tmp_path: Path) -> None:
    dataset_path = tmp_path / "conversations.json"
    dataset_path.write_text(json.dumps(FIXTURE_CONVERSATIONS), encoding="utf-8")

    train_examples, val_examples = db.build_dataset(path=dataset_path, val_fraction=0.2, seed=42)

    assert train_examples
    assert val_examples
    train_ids = {e["conversation_id"] for e in train_examples if e["conversation_id"] is not None}
    val_ids = {e["conversation_id"] for e in val_examples if e["conversation_id"] is not None}
    assert train_ids.isdisjoint(val_ids)

    assert "end" in {_target_decision(e) for e in val_examples}
    assert "end" in {_target_decision(e) for e in train_examples}


def test_hand_written_examples_are_train_only(tmp_path: Path) -> None:
    dataset_path = tmp_path / "conversations.json"
    dataset_path.write_text(json.dumps(FIXTURE_CONVERSATIONS), encoding="utf-8")

    train_examples, val_examples = db.build_dataset(path=dataset_path, val_fraction=0.2, seed=42)

    assert all(e["conversation_id"] is not None for e in val_examples)
    hand_written_in_train = [e for e in train_examples if e["conversation_id"] is None]
    assert len(hand_written_in_train) == len(db.HAND_WRITTEN_EXAMPLES)


def test_write_jsonl_produces_valid_lines(tmp_path: Path) -> None:
    dataset_path = tmp_path / "conversations.json"
    dataset_path.write_text(json.dumps(FIXTURE_CONVERSATIONS), encoding="utf-8")
    train_examples, val_examples = db.build_dataset(path=dataset_path, val_fraction=0.2, seed=42)

    out_path = tmp_path / "train.jsonl"
    db.write_jsonl(train_examples, out_path)

    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(train_examples)
    for line in lines:
        record = json.loads(line)
        messages = record["messages"]
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "assistant"
        target = json.loads(messages[-1]["content"])
        assert target["decision"] in {"end", "dont_end"}


def test_real_dataset_builds_without_leakage() -> None:
    train_examples, val_examples = db.build_dataset()

    assert train_examples
    assert val_examples
    train_ids = {e["conversation_id"] for e in train_examples if e["conversation_id"] is not None}
    val_ids = {e["conversation_id"] for e in val_examples if e["conversation_id"] is not None}
    assert train_ids.isdisjoint(val_ids)
