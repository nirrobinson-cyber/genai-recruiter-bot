"""Baseline comparison: prompted vs fine-tuned Exit Advisor (GRB-033, spec §5.2).

NOT a pytest test — makes real OpenAI calls over the held-out validation
split. Run manually:

    python -m app.modules.fine_tuning.compare

Scores both sides on the val split (`data/fine_tuning/exit_val.jsonl`) via
the real `exit_advisor.decide(history, model=...)` call path (same
retry/fallback/cache as production — see GRB-033's `model` override), and
reports precision/recall/F1 for `end` and `dont_end`. `end`-recall is the
headline metric (spec §5.2: missing an `end` costs more than a false `end` —
it means continuing to message an uninterested candidate).

If `settings.exit_advisor_finetuned_model` is empty (no fine-tuned model
exists), only the prompted row is scored — an expected, documented outcome
per the epic's own escape valve, not an error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.modules.exit_advisor import advisor as exit_advisor
from app.modules.fine_tuning.dataset_builder import VAL_PATH

_LABELS = ("end", "dont_end")


def load_val_examples(path: Path = VAL_PATH) -> list[dict[str, Any]]:
    """Reconstructs (history, gold_decision) pairs from the val JSONL —
    `history` strips the leading system message and trailing assistant
    target, matching what `exit_advisor.decide` expects."""

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    examples = []
    for line in lines:
        messages = json.loads(line)["messages"]
        history = messages[1:-1]
        gold = json.loads(messages[-1]["content"])["decision"]
        examples.append({"history": history, "gold": gold})
    return examples


def _metrics(golds: list[str], predictions: list[str]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for label in _LABELS:
        tp = sum(1 for g, p in zip(golds, predictions, strict=True) if g == label and p == label)
        fp = sum(1 for g, p in zip(golds, predictions, strict=True) if g != label and p == label)
        fn = sum(1 for g, p in zip(golds, predictions, strict=True) if g == label and p != label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        result[label] = {"precision": precision, "recall": recall, "f1": f1}
    return result


def _predict(examples: list[dict[str, Any]], model: str) -> list[str]:
    return [exit_advisor.decide(example["history"], model=model).decision for example in examples]


def compare_models(val_path: Path = VAL_PATH) -> dict[str, Any]:
    settings = get_settings()
    examples = load_val_examples(val_path)
    golds = [example["gold"] for example in examples]

    results: dict[str, Any] = {
        "prompted": {
            "model": settings.advisor_model,
            "metrics": _metrics(golds, _predict(examples, settings.advisor_model)),
        },
        "fine_tuned": None,
    }

    if settings.exit_advisor_finetuned_model:
        finetuned_predictions = _predict(examples, settings.exit_advisor_finetuned_model)
        results["fine_tuned"] = {
            "model": settings.exit_advisor_finetuned_model,
            "metrics": _metrics(golds, finetuned_predictions),
        }

    return results


def _print_table(results: dict[str, Any]) -> None:
    for key in ("prompted", "fine_tuned"):
        entry = results[key]
        if entry is None:
            print(f"\n{key}: not available (no fine-tuned model configured)")
            continue
        print(f"\n{key} ({entry['model']}):")
        for label, scores in entry["metrics"].items():
            print(
                f"  {label:9s} precision={scores['precision']:.2f} "
                f"recall={scores['recall']:.2f} f1={scores['f1']:.2f}"
            )


def main() -> None:
    results = compare_models()
    _print_table(results)


if __name__ == "__main__":
    main()
