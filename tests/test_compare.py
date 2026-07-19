"""Tests for the Exit Advisor baseline comparison (GRB-033).

No real API calls — `exit_advisor.decide` is mocked; metric math is checked
against a small hand-built (gold, predicted) set with a known-correct table.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.fine_tuning import compare
from app.schemas import ExitAdvisorOutput


def test_metrics_computes_precision_recall_f1() -> None:
    golds = ["end", "end", "dont_end", "dont_end", "end"]
    predictions = ["end", "dont_end", "dont_end", "end", "end"]
    # end: TP=2 (idx0,4) FP=1 (idx3) FN=1 (idx1) -> P=2/3 R=2/3
    # dont_end: TP=1 (idx2) FP=1 (idx1) FN=1 (idx3) -> P=1/2 R=1/2

    result = compare._metrics(golds, predictions)

    assert result["end"]["precision"] == pytest.approx(2 / 3)
    assert result["end"]["recall"] == pytest.approx(2 / 3)
    assert result["dont_end"]["precision"] == pytest.approx(0.5)
    assert result["dont_end"]["recall"] == pytest.approx(0.5)


def test_metrics_handles_no_predictions_for_a_class() -> None:
    golds = ["end", "end"]
    predictions = ["dont_end", "dont_end"]

    result = compare._metrics(golds, predictions)

    assert result["end"]["precision"] == 0.0
    assert result["end"]["recall"] == 0.0
    assert result["dont_end"]["precision"] == 0.0  # no true dont_end to be right about


def test_load_val_examples_strips_system_and_target(tmp_path: Path) -> None:
    val_path = tmp_path / "exit_val.jsonl"
    record = {
        "messages": [
            {"role": "system", "content": "task framing"},
            {"role": "assistant", "content": "opener"},
            {"role": "user", "content": "candidate reply"},
            {
                "role": "assistant",
                "content": json.dumps({"decision": "end", "confidence": 1.0, "reason": "r"}),
            },
        ]
    }
    val_path.write_text(json.dumps(record), encoding="utf-8")

    examples = compare.load_val_examples(val_path)

    assert len(examples) == 1
    assert examples[0]["gold"] == "end"
    assert examples[0]["history"] == [
        {"role": "assistant", "content": "opener"},
        {"role": "user", "content": "candidate reply"},
    ]


def test_compare_models_skips_fine_tuned_when_not_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    val_path = tmp_path / "exit_val.jsonl"
    record = {
        "messages": [
            {"role": "system", "content": "task framing"},
            {"role": "user", "content": "candidate reply"},
            {
                "role": "assistant",
                "content": json.dumps({"decision": "end", "confidence": 1.0, "reason": "r"}),
            },
        ]
    }
    val_path.write_text(json.dumps(record), encoding="utf-8")

    monkeypatch.setattr(
        compare.exit_advisor,
        "decide",
        lambda history, model=None: ExitAdvisorOutput(decision="end", confidence=1.0, reason="x"),
    )
    monkeypatch.setattr(compare.get_settings(), "exit_advisor_finetuned_model", "")

    results = compare.compare_models(val_path)

    assert results["prompted"] is not None
    assert results["fine_tuned"] is None
