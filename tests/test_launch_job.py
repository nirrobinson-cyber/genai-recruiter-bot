"""Tests for the Exit Advisor fine-tune launch/check script (GRB-032).

No real API calls — `get_client` is mocked with a fake OpenAI client double.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.modules.fine_tuning import launch_job


class _FakeFiles:
    def __init__(self) -> None:
        self.created: list[Any] = []

    def create(self, file: Any, purpose: str) -> SimpleNamespace:
        self.created.append((file, purpose))
        return SimpleNamespace(id=f"file-{len(self.created)}")


class _FakeJobs:
    def __init__(
        self, retrieve_status: str = "succeeded", fine_tuned_model: str | None = "ft:model"
    ) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.retrieve_calls: list[str] = []
        self._retrieve_status = retrieve_status
        self._fine_tuned_model = fine_tuned_model

    def create(
        self, training_file: str, validation_file: str, model: str, suffix: str
    ) -> SimpleNamespace:
        self.create_calls.append(
            {
                "training_file": training_file,
                "validation_file": validation_file,
                "model": model,
                "suffix": suffix,
            }
        )
        return SimpleNamespace(id="ftjob-abc123")

    def retrieve(self, job_id: str) -> SimpleNamespace:
        self.retrieve_calls.append(job_id)
        return SimpleNamespace(
            status=self._retrieve_status, fine_tuned_model=self._fine_tuned_model
        )


class _FakeClient:
    def __init__(self, jobs: _FakeJobs | None = None) -> None:
        self.files = _FakeFiles()
        self.fine_tuning = SimpleNamespace(jobs=jobs or _FakeJobs())


@pytest.fixture
def train_val_files(tmp_path: Path) -> tuple[Path, Path]:
    train_path = tmp_path / "exit_train.jsonl"
    val_path = tmp_path / "exit_val.jsonl"
    train_path.write_text('{"messages": []}\n', encoding="utf-8")
    val_path.write_text('{"messages": []}\n', encoding="utf-8")
    return train_path, val_path


def test_launch_uploads_files_and_creates_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, train_val_files: tuple[Path, Path]
) -> None:
    fake_client = _FakeClient()
    monkeypatch.setattr(launch_job, "get_client", lambda: fake_client)
    monkeypatch.setattr(launch_job, "STATUS_PATH", tmp_path / "job_status.json")

    train_path, val_path = train_val_files
    status = launch_job.launch(train_path=train_path, val_path=val_path)

    assert len(fake_client.files.created) == 2
    assert len(fake_client.fine_tuning.jobs.create_calls) == 1
    call = fake_client.fine_tuning.jobs.create_calls[0]
    assert call["training_file"] == "file-1"
    assert call["validation_file"] == "file-2"
    assert call["model"]  # base model forwarded from settings

    assert status["job_id"] == "ftjob-abc123"
    persisted = json.loads((tmp_path / "job_status.json").read_text(encoding="utf-8"))
    assert persisted["job_id"] == "ftjob-abc123"


def test_check_status_surfaces_fine_tuned_model_when_succeeded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    status_path = tmp_path / "job_status.json"
    status_path.write_text(
        json.dumps({"job_id": "ftjob-abc123", "status": "running", "fine_tuned_model": None}),
        encoding="utf-8",
    )
    monkeypatch.setattr(launch_job, "STATUS_PATH", status_path)

    fake_jobs = _FakeJobs(
        retrieve_status="succeeded", fine_tuned_model="ft:gpt-4o-mini:exit-advisor"
    )
    fake_client = _FakeClient(jobs=fake_jobs)
    monkeypatch.setattr(launch_job, "get_client", lambda: fake_client)

    status = launch_job.check_status()

    assert fake_jobs.retrieve_calls == ["ftjob-abc123"]
    assert status["status"] == "succeeded"
    assert status["fine_tuned_model"] == "ft:gpt-4o-mini:exit-advisor"
