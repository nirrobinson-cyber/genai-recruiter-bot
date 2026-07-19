"""Tests for the scheduling repository backed by SQLite."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from app.modules.sched_advisor.repository import ScheduleRepository
from app.modules.scheduling.db_setup import build_database


def test_repository_returns_only_available_slots(tmp_path: Path) -> None:
    db_path = tmp_path / "tech.db"
    build_database(2024, db_path=db_path)

    repository = ScheduleRepository(db_path=db_path)
    rows = repository.get_available_slots("Python Dev", date(2024, 1, 1), date(2024, 1, 2), limit=5)

    assert rows
    assert all(row["position"] == "Python Dev" for row in rows)
    assert all(row["available"] is True for row in rows)
    assert len(rows) <= 5


def test_booking_marks_slot_unavailable(tmp_path: Path) -> None:
    db_path = tmp_path / "tech.db"
    build_database(2024, db_path=db_path)

    repository = ScheduleRepository(db_path=db_path)
    with sqlite3.connect(db_path) as connection:
        first_schedule_id = connection.execute(
            "SELECT ScheduleID FROM Schedule WHERE available = 1 ORDER BY ScheduleID LIMIT 1"
        ).fetchone()[0]

    assert repository.book_slot(first_schedule_id) is True

    with sqlite3.connect(db_path) as connection:
        remaining = connection.execute(
            "SELECT available FROM Schedule WHERE ScheduleID = ?",
            (first_schedule_id,),
        ).fetchone()[0]

    assert remaining == 0
