"""SQLite-backed scheduling repository for GRB-011."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "tech.db"


class ScheduleRepository:
    """Simple repository for reading and updating scheduling slots."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DB_PATH)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def get_available_slots(
        self,
        position: str,
        from_date: date,
        to_date: date,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Return available slots for a position in the requested date range."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT ScheduleID, date, time, position, available
                FROM Schedule
                WHERE position = ?
                  AND date BETWEEN ? AND ?
                  AND available = 1
                ORDER BY date, time
                LIMIT ?
                """,
                (position, from_date.isoformat(), to_date.isoformat(), limit),
            ).fetchall()

        return [
            {
                "schedule_id": row[0],
                "date": row[1],
                "time": row[2],
                "position": row[3],
                "available": bool(row[4]),
            }
            for row in rows
        ]

    def book_slot(self, schedule_id: int) -> bool:
        """Mark a slot as unavailable and return whether the update affected a row."""

        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE Schedule SET available = 0 WHERE ScheduleID = ? AND available = 1",
                (schedule_id,),
            )
            connection.commit()
            return cursor.rowcount == 1
