"""Relative-date resolution for the Sched Advisor (spec §7.3).

Deterministic (dateutil-based), not LLM-assisted: the required expressions
("tomorrow", "next Friday", "Monday at 3 PM", "in two weeks") plus month-name
expressions ("April 2024") are all exactly resolvable this way, and keeping
date math deterministic avoids an unnecessary LLM call and non-determinism
in something that doesn't need it.

Returns `None` on an unrecognized expression rather than guessing — a wrong
guessed date presented with no signal anything went wrong is worse than
asking the candidate to clarify (see CLAUDE.md incident notes).
"""

from __future__ import annotations

import difflib
import re
from datetime import date, datetime, timedelta
from typing import NamedTuple

from dateutil.relativedelta import FR, MO, SA, SU, TH, TU, WE, relativedelta

SCHED_LOOKAHEAD_DAYS = 30
# SMS typing produces typos ("tomororw", "tommorow") constantly; a literal
# substring check silently misses them. "tomorrow" is compared against a
# single fixed target (unlike weekday names, which risk confusing e.g.
# Tuesday/Thursday at similarly high similarity), so fuzzy-matching it alone
# is safe: typo ratios (0.87-0.94) sit far above unrelated words like
# "today"/"tom" (0.31-0.55).
_TOMORROW_FUZZY_CUTOFF = 0.82


class DateRange(NamedTuple):
    """Inclusive search window for `get_available_slots`."""

    from_date: date
    to_date: date


_WEEKDAYS = {
    "monday": MO,
    "tuesday": TU,
    "wednesday": WE,
    "thursday": TH,
    "friday": FR,
    "saturday": SA,
    "sunday": SU,
}

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_WEEKS_PATTERN = re.compile(r"in\s+(\w+)\s+weeks?", re.IGNORECASE)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4}
_MONTH_PATTERN = re.compile(r"\b(" + "|".join(_MONTHS) + r")\b(?:\s+(\d{4}))?", re.IGNORECASE)
# Day-first numeric dates (d/m/yy, dd/mm/yyyy, ...) — this project uses the IL
# (day-first) calendar convention throughout, not US month-first.
_NUMERIC_DATE_PATTERN = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})\b")


def _looks_like_tomorrow(lowered: str) -> bool:
    if "tomorrow" in lowered:
        return True
    tokens = re.findall(r"[a-z]+", lowered)
    return any(
        difflib.SequenceMatcher(None, token, "tomorrow").ratio() >= _TOMORROW_FUZZY_CUTOFF
        for token in tokens
    )


def default_forward_window(now: datetime) -> DateRange:
    """Nearest-available-slots window for when the candidate hasn't named any
    date at all (e.g. just shared qualifying background, or declined a
    specific time without proposing a new one) — the Sched Advisor uses this
    to proactively offer the soonest options instead of asking an
    open-ended "when works?" question."""
    today = now.date()
    return _forward_window(today + timedelta(days=1), today)


def _forward_window(anchor: date, today: date) -> DateRange:
    """A single-day match keeps the existing forward-looking search window,
    so "3 nearest slots" behavior still works when the exact day has none."""

    anchor = max(anchor, today + timedelta(days=1))
    return DateRange(anchor, anchor + timedelta(days=SCHED_LOOKAHEAD_DAYS))


def resolve_relative_date(expression: str, now: datetime) -> DateRange | None:
    """Resolve a relative-date expression to a concrete search window.

    Returns `None` if the expression doesn't match a known pattern — callers
    must treat that as "ask the candidate to clarify", never as "tomorrow".
    """

    lowered = expression.lower()
    today = now.date()

    if _looks_like_tomorrow(lowered):
        return _forward_window(today + timedelta(days=1), today)

    numeric_match = _NUMERIC_DATE_PATTERN.search(lowered)
    if numeric_match:
        day_str, month_str, year_str = numeric_match.groups()
        year = int(year_str)
        if year < 100:
            year += 2000
        try:
            candidate = date(year, int(month_str), int(day_str))
        except ValueError:
            return None
        return _forward_window(candidate, today)

    weeks_match = _WEEKS_PATTERN.search(lowered)
    if weeks_match:
        count = _NUMBER_WORDS.get(weeks_match.group(1))
        if count is None:
            try:
                count = int(weeks_match.group(1))
            except ValueError:
                count = 2
        return _forward_window(today + timedelta(weeks=count), today)

    month_match = _MONTH_PATTERN.search(lowered)
    if month_match:
        month_num = _MONTHS[month_match.group(1).lower()]
        year_str = month_match.group(2)
        year = int(year_str) if year_str else today.year

        from_date = date(year, month_num, 1)
        to_date = from_date + relativedelta(day=31)
        if not year_str and to_date < today:
            from_date += relativedelta(years=1)
            to_date += relativedelta(years=1)

        from_date = max(from_date, today + timedelta(days=1))
        return DateRange(from_date, to_date)

    for name, weekday in _WEEKDAYS.items():
        if name in lowered:
            candidate = today + relativedelta(weekday=weekday(+1))
            # dateutil's weekday(+1) means "on or after", not "strictly after" —
            # "next Friday" said on a Friday must mean the following week.
            if candidate == today:
                candidate += timedelta(weeks=1)
            return _forward_window(candidate, today)

    return None
