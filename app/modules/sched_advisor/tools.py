"""LangChain tools wrapping ScheduleRepository (spec §7.2). Reused, not reimplemented."""

from __future__ import annotations

from datetime import date

from langchain_core.tools import tool

from app.modules.sched_advisor.repository import DB_PATH, ScheduleRepository


@tool
def get_available_slots(position: str, from_date: str, to_date: str, limit: int = 3) -> list[dict]:
    """Return up to `limit` earliest available interview slots for `position`
    between from_date and to_date (ISO dates), ordered by date, time."""
    repository = ScheduleRepository(db_path=DB_PATH)
    return repository.get_available_slots(
        position, date.fromisoformat(from_date), date.fromisoformat(to_date), limit=limit
    )


@tool
def book_slot(schedule_id: int) -> dict:
    """Mark the slot as booked (available=0). Returns a confirmation payload."""
    repository = ScheduleRepository(db_path=DB_PATH)
    booked = repository.book_slot(schedule_id)
    return {"schedule_id": schedule_id, "booked": booked}
