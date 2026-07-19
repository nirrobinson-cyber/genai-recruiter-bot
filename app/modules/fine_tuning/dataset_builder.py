"""Exit Advisor fine-tuning dataset builder (GRB-030, GRB-031, spec §5.2).

Turns labeled conversations from `data/raw/sms_conversations.json` into
OpenAI chat fine-tuning JSONL. Each training example matches the exact
message shape the real advisor sends at inference
(`app.llm_client.history_to_messages` + the real `SYSTEM_PROMPT`) so there is
no train/serve skew, and the assistant target is the same JSON shape
`ExitAdvisorOutput` requires (`cached_parse(..., response_format=ExitAdvisorOutput)`)
rather than a bare label token the model would never actually be asked to
produce.

Split is at the CONVERSATION level (never turn level) to avoid leakage
between train and validation.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.llm_client import history_to_messages
from app.modules.exit_advisor.prompts import SYSTEM_PROMPT

TRAIN_PATH = Path("data/fine_tuning/exit_train.jsonl")
VAL_PATH = Path("data/fine_tuning/exit_val.jsonl")

_LABEL_MAP = {"end": "end", "continue": "dont_end", "schedule": "dont_end"}
_REASON = {
    "end": "candidate reply indicates the conversation should end",
    "dont_end": "candidate reply does not indicate the conversation should end",
}


def _role(speaker: str) -> str:
    return "user" if speaker == "candidate" else "assistant"


def _target_message(decision: str) -> dict[str, str]:
    content = json.dumps({"decision": decision, "confidence": 1.0, "reason": _REASON[decision]})
    return {"role": "assistant", "content": content}


def build_examples(conversations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One example per labeled recruiter turn that has preceding history.

    Each example carries `conversation_id` (for split bookkeeping) alongside
    the `messages` list OpenAI's fine-tuning format expects.
    """

    examples: list[dict[str, Any]] = []
    for conversation in conversations:
        turns = conversation["turns"]
        for index, turn in enumerate(turns):
            if turn["speaker"] != "recruiter" or turn.get("label") is None:
                continue
            if index == 0:
                continue
            decision = _LABEL_MAP[turn["label"]]
            history = [{"role": _role(t["speaker"]), "content": t["text"]} for t in turns[:index]]
            messages = history_to_messages(SYSTEM_PROMPT, history) + [_target_message(decision)]
            examples.append(
                {"conversation_id": conversation["conversation_id"], "messages": messages}
            )
    return examples


def split_conversation_ids(
    conversations: list[dict[str, Any]], val_fraction: float = 0.2, seed: int = 42
) -> tuple[list[int], list[int]]:
    """Deterministic conversation-level split — never split a conversation's
    turns across train/val."""

    ids = [conversation["conversation_id"] for conversation in conversations]
    shuffled = ids[:]
    random.Random(seed).shuffle(shuffled)
    val_size = max(1, round(len(shuffled) * val_fraction))
    val_ids = shuffled[:val_size]
    train_ids = shuffled[val_size:]
    return train_ids, val_ids


# --- GRB-031: hand-authored edge cases, appended to TRAIN only -------------
# Not derived from data/raw/sms_conversations.json — written to cover
# patterns underrepresented in the 15 dataset conversations.

_HAND_WRITTEN_RAW: list[tuple[list[tuple[str, str]], str]] = [
    (
        [("candidate", "Please stop texting me, I'm not interested.")],
        "end",
    ),
    (
        [("candidate", "Remove me from your list, thanks.")],
        "end",
    ),
    (
        [("candidate", "Take me off your texting list please.")],
        "end",
    ),
    (
        [("candidate", "I'll be in touch.")],
        "dont_end",
    ),
    (
        [("candidate", "Let me think about it and get back to you.")],
        "dont_end",
    ),
    (
        [
            ("assistant", "Our engineering manager can interview you Wednesday at 10 AM."),
            ("candidate", "Wednesday at 10 works for me."),
        ],
        "end",
    ),
    (
        [
            ("assistant", "We can offer Tuesday at 2 PM or Thursday at 4 PM."),
            ("candidate", "Tuesday at 2 PM sounds good, let's do that."),
        ],
        "end",
    ),
    (
        [
            ("assistant", "How about Monday at 3 PM for the interview?"),
            ("candidate", "Can we do a different time? Monday doesn't work."),
        ],
        "dont_end",
    ),
    (
        [
            ("assistant", "Would Friday at 11 AM work for an interview?"),
            ("candidate", "Do you have anything the following week instead?"),
        ],
        "dont_end",
    ),
    (
        [("candidate", "I actually just accepted a job with another company, sorry.")],
        "end",
    ),
    (
        [("candidate", "I'm no longer looking, but thanks for reaching out.")],
        "end",
    ),
    (
        [("candidate", "What's the salary range for this role?")],
        "dont_end",
    ),
    (
        [("candidate", "Not right now, maybe check back with me in a few months.")],
        "dont_end",
    ),
]


def _build_hand_written_examples() -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for history_pairs, decision in _HAND_WRITTEN_RAW:
        history = [{"role": role, "content": text} for role, text in history_pairs]
        messages = history_to_messages(SYSTEM_PROMPT, history) + [_target_message(decision)]
        examples.append({"conversation_id": None, "messages": messages})
    return examples


HAND_WRITTEN_EXAMPLES = _build_hand_written_examples()


def build_dataset(
    path: Path | None = None, val_fraction: float = 0.2, seed: int = 42
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load, split by conversation, build examples, append train-only augmentation."""

    dataset_path = path or Path(get_settings().conversations_json)
    conversations = json.loads(dataset_path.read_text(encoding="utf-8"))

    train_ids, val_ids = split_conversation_ids(conversations, val_fraction, seed)
    train_ids_set, val_ids_set = set(train_ids), set(val_ids)

    all_examples = build_examples(conversations)
    train_examples = [e for e in all_examples if e["conversation_id"] in train_ids_set]
    val_examples = [e for e in all_examples if e["conversation_id"] in val_ids_set]

    train_examples = train_examples + HAND_WRITTEN_EXAMPLES
    return train_examples, val_examples


def write_jsonl(examples: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"messages": example["messages"]}) for example in examples]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _count_labels(examples: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"end": 0, "dont_end": 0}
    for example in examples:
        decision = json.loads(example["messages"][-1]["content"])["decision"]
        counts[decision] += 1
    return counts


def main() -> None:
    train_examples, val_examples = build_dataset()
    write_jsonl(train_examples, TRAIN_PATH)
    write_jsonl(val_examples, VAL_PATH)
    print(f"train: {len(train_examples)} examples -> {TRAIN_PATH} {_count_labels(train_examples)}")
    print(f"val:   {len(val_examples)} examples -> {VAL_PATH} {_count_labels(val_examples)}")


if __name__ == "__main__":
    main()
