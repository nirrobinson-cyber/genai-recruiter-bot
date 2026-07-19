"""Create and seed the SQLite scheduling database for Epic E1 GRB-010.

This module ports the SQL Server schema and seed logic from data/raw/db_Tech.sql
into a local SQLite database at data/tech.db.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date, time, timedelta
from pathlib import Path
from random import Random

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "tech.db"

POSITIONS = ["Python Dev", "Sql Dev", "Analyst", "ML"]
START_HOUR = 9
END_HOUR = 17
ALLOWED_WEEKDAYS = {1, 2, 3, 4, 6}  # Tuesday-Friday and Sunday


def _iter_dates(year: int) -> Iterable[date]:
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _iter_times() -> Iterable[time]:
    current_hour = START_HOUR
    while current_hour < END_HOUR:
        yield time(current_hour, 0)
        current_hour += 1


def build_database(year: int = 2024, *, db_path: Path | None = None) -> Path:
    """Create the SQLite database and seed it with scheduling slots.

    Parameters
    ----------
    year:
        Seed year to generate.
    db_path:
        Optional override for the output database path.
    """

    target_db = db_path or DB_PATH
    target_db.parent.mkdir(parents=True, exist_ok=True)
    if target_db.exists():
        target_db.unlink()

    rng = Random(year)
    connection = sqlite3.connect(target_db)
    try:
        connection.execute(
            """
            CREATE TABLE Schedule (
                ScheduleID INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                position TEXT NOT NULL,
                available INTEGER NOT NULL CHECK (available IN (0, 1))
            )
            """
        )

        rows: list[tuple[str, str, str, int]] = []
        for day in _iter_dates(year):
            if day.weekday() not in ALLOWED_WEEKDAYS:
                continue
            for slot_time in _iter_times():
                for position in POSITIONS:
                    rows.append(
                        (
                            day.isoformat(),
                            slot_time.strftime("%H:%M:%S"),
                            position,
                            1 if rng.random() >= 0.5 else 0,
                        )
                    )

        connection.executemany(
            "INSERT INTO Schedule (date, time, position, available) VALUES (?, ?, ?, ?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()

    return target_db


def main() -> None:
    """CLI entry point for creating the SQLite scheduling database."""

    target_db = build_database()
    print(f"Created scheduling database at {target_db}")


if __name__ == "__main__":
    main()
