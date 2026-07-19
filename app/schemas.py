"""Uniform AdvisorOutput Pydantic contracts (GRB-020, spec §5.1-§5.4, rule N-3).

Every LLM decision in this system is parsed into one of these schemas instead
of free-text — see app.structured_output for the retry/fallback wrapper that
enforces this.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExitAdvisorOutput(BaseModel):
    """Spec §5.2 output contract."""

    decision: Literal["end", "dont_end"]
    confidence: float
    reason: str


class SlotProposal(BaseModel):
    schedule_id: int
    date: str
    time: str


class SchedAdvisorOutput(BaseModel):
    """Spec §5.3 output contract.

    "confirmed" is a booking-completion decision (spec A-4: booking = flipping
    `available` to 0): the candidate accepted one of the *previously offered*
    slots. `confirmed_schedule_id` is only ever the model's pointer to which
    offered slot — never trusted for date/time itself (S-3 discipline); once
    validated, the matched slot is placed in `proposed_slots` too.
    """

    decision: Literal["sched", "dont_sched", "confirmed"]
    proposed_slots: list[SlotProposal] = Field(default_factory=list)
    confirmed_schedule_id: int | None = None
    reason: str


class InfoAdvisorOutput(BaseModel):
    """Spec §5.4 output contract."""

    decision: Literal["info_needed", "info_not_needed"]
    draft_answer: str | None = None
    sources: list[str] = Field(default_factory=list)
    reason: str


class MainAgentOutput(BaseModel):
    """Spec §5.1 output contract (rule R-5: exactly one action label per turn)."""

    action: Literal["continue", "schedule", "end"]
    message: str
    consulted: list[str] = Field(default_factory=list)
    rationale: str = ""


class RoutingDecision(BaseModel):
    """Main Agent's per-iteration decision (flowchart nodes decide_3_options +
    decide_final, spec §4): which advisor to consult next, or "respond" to
    stop consulting and synthesize a reply this turn.

    `candidate_shared_experience` is a side-channel signal (no extra API
    call) feeding the proactive-escalation state flag (spec §5.1: "the
    conversation has matured enough to offer one") — set true whenever the
    candidate's latest message describes their background/experience/skills,
    regardless of `next_step`.
    """

    next_step: Literal["exit", "sched", "info", "respond"]
    reason: str
    candidate_shared_experience: bool = False
