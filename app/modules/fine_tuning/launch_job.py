"""Launch and check the Exit Advisor fine-tuning job (GRB-032, spec §5.2).

Usage:
    python -m app.modules.fine_tuning.launch_job launch   # upload files + create job
    python -m app.modules.fine_tuning.launch_job check     # poll job status

Never writes `EXIT_ADVISOR_FINETUNED_MODEL` into `.env` automatically — once
`check` reports `succeeded`, it prints the model ID and the exact line to
add, left for a human (or an explicit follow-up) to apply.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.llm_client import get_client
from app.modules.fine_tuning.dataset_builder import TRAIN_PATH, VAL_PATH

STATUS_PATH = Path("data/fine_tuning/job_status.json")


def upload_training_files(
    train_path: Path = TRAIN_PATH, val_path: Path = VAL_PATH
) -> tuple[str, str]:
    client = get_client()
    with train_path.open("rb") as handle:
        train_file = client.files.create(file=handle, purpose="fine-tune")
    with val_path.open("rb") as handle:
        val_file = client.files.create(file=handle, purpose="fine-tune")
    return train_file.id, val_file.id


def create_fine_tune_job(
    training_file_id: str,
    validation_file_id: str,
    base_model: str,
    suffix: str = "exit-advisor",
) -> str:
    client = get_client()
    job = client.fine_tuning.jobs.create(
        training_file=training_file_id,
        validation_file=validation_file_id,
        model=base_model,
        suffix=suffix,
    )
    return job.id


def _write_status(status: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")


def _read_status() -> dict:
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def launch(train_path: Path = TRAIN_PATH, val_path: Path = VAL_PATH) -> dict:
    settings = get_settings()
    training_file_id, validation_file_id = upload_training_files(train_path, val_path)
    job_id = create_fine_tune_job(
        training_file_id, validation_file_id, settings.fine_tune_base_model
    )

    status = {
        "job_id": job_id,
        "base_model": settings.fine_tune_base_model,
        "training_file_id": training_file_id,
        "validation_file_id": validation_file_id,
        "status": "created",
        "fine_tuned_model": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _write_status(status)
    return status


def check_status(job_id: str | None = None) -> dict:
    status = _read_status()
    target_job_id = job_id or status["job_id"]

    client = get_client()
    job = client.fine_tuning.jobs.retrieve(target_job_id)

    status["status"] = job.status
    status["fine_tuned_model"] = job.fine_tuned_model
    status["checked_at"] = datetime.now(UTC).isoformat()
    _write_status(status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["launch", "check"])
    args = parser.parse_args()

    if args.command == "launch":
        status = launch()
        print(f"Launched job {status['job_id']} (base model {status['base_model']})")
        print(f"Status persisted to {STATUS_PATH}")
    else:
        status = check_status()
        print(f"Job {status['job_id']}: {status['status']}")
        if status["status"] == "succeeded":
            print(f"Fine-tuned model: {status['fine_tuned_model']}")
            print(f"To use it: EXIT_ADVISOR_FINETUNED_MODEL={status['fine_tuned_model']}")


if __name__ == "__main__":
    main()
