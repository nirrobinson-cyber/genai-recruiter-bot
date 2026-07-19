"""Tests for resolve_relative_date (spec §7.3) with a fixed `now`."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.modules.sched_advisor.date_resolver import (
    SCHED_LOOKAHEAD_DAYS,
    DateRange,
    default_forward_window,
    resolve_relative_date,
)

# Fixed reference point: Wednesday, 2024-04-17.
NOW = datetime(2024, 4, 17, 9, 0, 0)


def test_tomorrow() -> None:
    result = resolve_relative_date("tomorrow", NOW)
    assert result == DateRange(
        date(2024, 4, 18), date(2024, 4, 18) + timedelta(days=SCHED_LOOKAHEAD_DAYS)
    )


def test_next_friday() -> None:
    result = resolve_relative_date("next Friday", NOW)
    assert result.from_date == date(2024, 4, 19)


def test_monday_at_3_pm() -> None:
    result = resolve_relative_date("Monday at 3 PM", NOW)
    assert result.from_date == date(2024, 4, 22)


def test_in_two_weeks() -> None:
    result = resolve_relative_date("in two weeks", NOW)
    assert result.from_date == date(2024, 5, 1)


def test_next_weekday_on_the_same_weekday_rolls_to_next_week() -> None:
    wednesday_now = datetime(2024, 4, 17, 9, 0, 0)
    result = resolve_relative_date("next Wednesday", wednesday_now)
    assert result.from_date == date(2024, 4, 24)


def test_month_and_year_resolves_to_tight_month_range() -> None:
    result = resolve_relative_date("April 2024?", NOW)
    assert result == DateRange(date(2024, 4, 18), date(2024, 4, 30))  # clamped past today (4/17)


def test_month_and_year_full_range_when_month_is_entirely_future() -> None:
    result = resolve_relative_date("December 2024", NOW)
    assert result == DateRange(date(2024, 12, 1), date(2024, 12, 31))


def test_month_without_year_uses_current_year() -> None:
    result = resolve_relative_date("in August", NOW)
    assert result == DateRange(date(2024, 8, 1), date(2024, 8, 31))


def test_month_without_year_rolls_to_next_year_if_already_passed() -> None:
    result = resolve_relative_date("January", NOW)
    assert result == DateRange(date(2025, 1, 1), date(2025, 1, 31))


def test_unrecognized_expression_returns_none_not_tomorrow() -> None:
    """Critical safety behavior: an unresolvable expression must never
    silently guess "tomorrow" — callers must ask the candidate to clarify."""
    assert resolve_relative_date("whenever works for you", NOW) is None


def test_numeric_date_d_m_yy_is_day_first() -> None:
    """14/4/24 must resolve to 14 April 2024, not 4 Dec 2024 (US month-first) —
    this project uses the IL/day-first calendar convention throughout."""
    result = resolve_relative_date("14/4/24", NOW)
    assert result.from_date == date(2024, 4, 18)  # clamped forward past NOW (4/17)


def test_numeric_date_dd_mm_yyyy() -> None:
    result = resolve_relative_date("Can we do 25/12/2024?", NOW)
    assert result.from_date == date(2024, 12, 25)


def test_numeric_date_future_day_not_clamped() -> None:
    result = resolve_relative_date("20/4/24", NOW)
    assert result.from_date == date(2024, 4, 20)


def test_numeric_date_invalid_returns_none() -> None:
    """A syntactically date-shaped but impossible date (month 13) must
    surface as unresolved, never silently guessed or crash."""
    assert resolve_relative_date("32/13/24", NOW) is None


def test_tomorrow_typo_tomororw() -> None:
    """Reported bug: SMS typos like "tomororw" (a transposition of
    "tomorrow") were silently unresolved instead of recognized."""
    result = resolve_relative_date("can we schedule for tomororw?", NOW)
    assert result == DateRange(
        date(2024, 4, 18), date(2024, 4, 18) + timedelta(days=SCHED_LOOKAHEAD_DAYS)
    )


def test_tomorrow_typo_tommorow() -> None:
    result = resolve_relative_date("tommorow works for me", NOW)
    assert result.from_date == date(2024, 4, 18)


def test_today_is_not_confused_with_tomorrow() -> None:
    """ "today" must stay unresolved (not a supported expression), not get
    fuzzy-matched to "tomorrow" — the typo tolerance must not overreach."""
    assert resolve_relative_date("today", NOW) is None


def test_default_forward_window_starts_tomorrow() -> None:
    result = default_forward_window(NOW)
    assert result == DateRange(
        date(2024, 4, 18), date(2024, 4, 18) + timedelta(days=SCHED_LOOKAHEAD_DAYS)
    )
