"""Tests for the Sched Advisor (GRB-023). No real API/DB calls — mocked."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.modules.sched_advisor import advisor
from app.modules.sched_advisor.advisor import _looks_like_a_date_attempt
from app.schemas import SchedAdvisorOutput, SlotProposal

NOW = datetime(2024, 4, 17, 9, 0, 0)


@pytest.mark.parametrize(
    "message",
    ["Yes, 3 years' experience", "I have 5 years of experience", "3 years", "5+ years in Python"],
)
def test_years_of_experience_with_a_numeral_is_not_a_date_attempt(message: str) -> None:
    """Regression test: a bare digit used to match ANY number, wrongly
    flagging "3 years' experience" as a garbled date attempt (blocking the
    proactive-offer fallback) while spelled-out "five years" worked fine."""
    assert _looks_like_a_date_attempt(message) is False


@pytest.mark.parametrize(
    "message", ["14/4/24", "Monday at 3 PM is good.", "the 14th works", "10am works for me"]
)
def test_real_date_or_time_attempts_are_still_detected(message: str) -> None:
    assert _looks_like_a_date_attempt(message) is True


class _FakeTool:
    def __init__(self, rows: list[dict] | dict | None = None) -> None:
        self.rows = rows
        self.calls: list[dict] = []

    def invoke(self, kwargs: dict):
        self.calls.append(kwargs)
        return self.rows


def test_decide_dont_sched_never_touches_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        advisor,
        "_call_llm",
        lambda history, offered_slots: SchedAdvisorOutput(
            decision="dont_sched", proposed_slots=[], reason="not ready"
        ),
    )
    fake_tool = _FakeTool(rows=[])
    monkeypatch.setattr(advisor, "get_available_slots", fake_tool)

    result = advisor.decide([{"role": "user", "content": "tell me more first"}], now=NOW)

    assert result.decision == "dont_sched"
    assert fake_tool.calls == []  # R-3: SQL only queried when advisor rules "sched"


def test_decide_sched_overwrites_llm_slots_with_verified_db_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        advisor,
        "_call_llm",
        lambda history, offered_slots: SchedAdvisorOutput(
            decision="sched",
            proposed_slots=[SlotProposal(schedule_id=999, date="2099-01-01", time="00:00:00")],
            reason="candidate asked to schedule",
        ),
    )
    fake_tool = _FakeTool(
        rows=[
            {
                "schedule_id": 42,
                "date": "2024-04-18",
                "time": "10:00:00",
                "position": "Python Dev",
                "available": True,
            }
        ]
    )
    monkeypatch.setattr(advisor, "get_available_slots", fake_tool)

    result = advisor.decide([{"role": "user", "content": "Can we schedule tomorrow?"}], now=NOW)

    assert result.decision == "sched"
    assert [slot.schedule_id for slot in result.proposed_slots] == [42]
    assert fake_tool.calls[0]["from_date"] == "2024-04-18"


def test_decide_sched_with_garbled_date_attempt_asks_to_clarify_and_never_touches_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the candidate clearly attempted to name a date/day but it can't be
    resolved, decide() must not guess a specific wrong date — it should
    decline and ask to clarify."""
    monkeypatch.setattr(
        advisor,
        "_call_llm",
        lambda history, offered_slots: SchedAdvisorOutput(
            decision="sched", proposed_slots=[], reason="candidate wants to schedule"
        ),
    )
    fake_tool = _FakeTool(rows=[])
    monkeypatch.setattr(advisor, "get_available_slots", fake_tool)

    result = advisor.decide(
        [{"role": "user", "content": "Can we do it sometime next week?"}], now=NOW
    )

    assert result.decision == "dont_sched"
    assert "clarify" in result.reason
    assert fake_tool.calls == []


def test_decide_sched_with_no_date_named_defaults_to_nearest_available_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If no date was named at all (candidate deferred entirely, e.g.
    "whenever works for you"), decide() should proactively offer the
    nearest available slots rather than asking an open-ended clarifying
    question — there's nothing ambiguous to clarify, they explicitly left
    it up to us."""
    monkeypatch.setattr(
        advisor,
        "_call_llm",
        lambda history, offered_slots: SchedAdvisorOutput(
            decision="sched", proposed_slots=[], reason="candidate deferred to us"
        ),
    )
    fake_tool = _FakeTool(
        rows=[
            {
                "schedule_id": 7,
                "date": "2024-04-18",
                "time": "09:00:00",
                "position": "Python Dev",
                "available": True,
            }
        ]
    )
    monkeypatch.setattr(advisor, "get_available_slots", fake_tool)

    result = advisor.decide([{"role": "user", "content": "whenever works for you"}], now=NOW)

    assert result.decision == "sched"
    assert [slot.schedule_id for slot in result.proposed_slots] == [7]
    assert fake_tool.calls[0]["from_date"] == "2024-04-18"


def test_decide_rejection_with_no_date_advances_past_previously_offered_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for the reported bug: rejecting the offered batch
    ("none") with no new date named used to always search from `now`,
    re-surfacing the very first (earliest) slots. Must instead search from
    after the latest previously-offered date, and exclude those exact ids
    even if the DB happens to return them again."""
    monkeypatch.setattr(
        advisor,
        "_call_llm",
        lambda history, offered_slots: SchedAdvisorOutput(
            decision="sched", proposed_slots=[], reason="candidate rejected the offered batch"
        ),
    )
    fake_tool = _FakeTool(
        rows=[
            {"schedule_id": 1, "date": "2024-04-18", "time": "09:00:00"},  # already offered
            {"schedule_id": 2, "date": "2024-05-16", "time": "10:00:00"},  # genuinely new
        ]
    )
    monkeypatch.setattr(advisor, "get_available_slots", fake_tool)
    previously_offered = [{"schedule_id": 1, "date": "2024-04-18", "time": "09:00:00"}]

    result = advisor.decide(
        [{"role": "user", "content": "none"}],
        now=NOW,
        previously_offered_slots=previously_offered,
    )

    assert result.decision == "sched"
    assert [slot.schedule_id for slot in result.proposed_slots] == [2]
    assert (
        fake_tool.calls[0]["from_date"] == "2024-04-19"
    )  # day after the previous offer, not `now`
    assert fake_tool.calls[0]["limit"] == 4  # 3 + len(excluded_ids)


def test_decide_sched_with_no_further_slots_after_exclusion_reports_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        advisor,
        "_call_llm",
        lambda history, offered_slots: SchedAdvisorOutput(
            decision="sched", proposed_slots=[], reason="candidate rejected the offered batch"
        ),
    )
    fake_tool = _FakeTool(rows=[{"schedule_id": 1, "date": "2024-04-18", "time": "09:00:00"}])
    monkeypatch.setattr(advisor, "get_available_slots", fake_tool)
    previously_offered = [{"schedule_id": 1, "date": "2024-04-18", "time": "09:00:00"}]

    result = advisor.decide(
        [{"role": "user", "content": "none"}],
        now=NOW,
        previously_offered_slots=previously_offered,
    )

    assert result.decision == "sched"
    assert result.proposed_slots == []


def test_call_llm_annotates_offered_slots_with_weekday_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: the LLM used to be given only raw ISO dates and had
    to compute the day-of-week itself to match a candidate's weekday
    reference ("Friday 11 AM") against an offered slot — an error-prone
    calculation for a model. The offered-slots block must spell out the
    weekday name so the model never has to do that math."""
    captured: dict = {}

    def fake_cached_parse(**kwargs):
        captured.update(kwargs)
        return SchedAdvisorOutput(decision="dont_sched", proposed_slots=[], reason="n/a")

    monkeypatch.setattr(advisor, "cached_parse", fake_cached_parse)

    advisor._call_llm(
        [{"role": "user", "content": "Friday 11 AM sounds great."}],
        offered_slots=[{"schedule_id": 42, "date": "2024-04-19", "time": "11:00:00"}],
    )

    slots_message = next(m for m in captured["messages"] if "Offered slots" in m["content"])
    assert "2024-04-19 (Friday) 11:00:00" in slots_message["content"]


def test_decide_falls_back_when_llm_call_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def always_fails(
        history: list[dict[str, str]], offered_slots: list[dict]
    ) -> SchedAdvisorOutput:
        raise RuntimeError("simulated API failure")

    monkeypatch.setattr(advisor, "_call_llm", always_fails)

    result = advisor.decide([{"role": "user", "content": "..."}], now=NOW)

    assert result is advisor.FALLBACK
    assert result.decision == "dont_sched"


OFFERED = [{"schedule_id": 42, "date": "2024-04-22", "time": "15:00:00"}]


def test_decide_confirmed_books_the_matched_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        advisor,
        "_call_llm",
        lambda history, offered_slots: SchedAdvisorOutput(
            decision="confirmed",
            confirmed_schedule_id=42,
            proposed_slots=[],
            reason="candidate accepted the slot",
        ),
    )
    fake_book_slot = _FakeTool(rows={"schedule_id": 42, "booked": True})
    monkeypatch.setattr(advisor, "book_slot", fake_book_slot)

    result = advisor.decide(
        [{"role": "user", "content": "Monday at 3 PM is good."}], now=NOW, offered_slots=OFFERED
    )

    assert result.decision == "confirmed"
    assert result.confirmed_schedule_id == 42
    assert result.proposed_slots == [
        SlotProposal(schedule_id=42, date="2024-04-22", time="15:00:00")
    ]
    assert fake_book_slot.calls == [{"schedule_id": 42}]


def test_decide_confirmed_id_not_in_offered_slots_is_not_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defends against a hallucinated confirmed_schedule_id that was never
    actually offered — never books, never trusts the model here (S-3)."""
    monkeypatch.setattr(
        advisor,
        "_call_llm",
        lambda history, offered_slots: SchedAdvisorOutput(
            decision="confirmed",
            confirmed_schedule_id=999,
            proposed_slots=[],
            reason="candidate accepted the slot",
        ),
    )
    fake_book_slot = _FakeTool()
    monkeypatch.setattr(advisor, "book_slot", fake_book_slot)

    result = advisor.decide(
        [{"role": "user", "content": "Monday at 3 PM is good."}], now=NOW, offered_slots=OFFERED
    )

    assert result.decision == "dont_sched"
    assert fake_book_slot.calls == []


def test_decide_confirmed_but_slot_no_longer_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        advisor,
        "_call_llm",
        lambda history, offered_slots: SchedAdvisorOutput(
            decision="confirmed",
            confirmed_schedule_id=42,
            proposed_slots=[],
            reason="candidate accepted the slot",
        ),
    )
    fake_book_slot = _FakeTool(rows={"schedule_id": 42, "booked": False})
    monkeypatch.setattr(advisor, "book_slot", fake_book_slot)

    result = advisor.decide(
        [{"role": "user", "content": "Monday at 3 PM is good."}], now=NOW, offered_slots=OFFERED
    )

    assert result.decision == "dont_sched"
    assert "no longer available" in result.reason
