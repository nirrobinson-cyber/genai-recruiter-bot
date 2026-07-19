"""Main Agent routing (spec §5.1) — decides which advisor to consult next, or
to respond, given the full chat history and this turn's consultations so far.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.llm_client import cached_parse, history_to_messages
from app.modules.main_agent.prompts import SYSTEM_PROMPT
from app.schemas import RoutingDecision
from app.structured_output import get_structured_output

FALLBACK = RoutingDecision(
    next_step="respond",
    reason="LLM routing failed after retry; defaulting to asking for clarification",
)


def _call_llm(
    history: list[dict[str, str]],
    consultations_so_far: list[dict[str, Any]],
    last_action: str | None,
    qualifying_info_shared: bool,
    slots_already_offered: bool,
) -> RoutingDecision:
    settings = get_settings()
    messages = history_to_messages(SYSTEM_PROMPT, history)
    if last_action is not None:
        messages.append(
            {"role": "system", "content": f"The previous turn's action was '{last_action}'."}
        )
    if qualifying_info_shared and not slots_already_offered:
        messages.append(
            {
                "role": "system",
                "content": "Qualifying info has already been shared and no interview slots have been offered yet.",
            }
        )
    if consultations_so_far:
        summary = "\n".join(
            f"- {entry['advisor']}: {entry['output']}" for entry in consultations_so_far
        )
        messages.append(
            {"role": "system", "content": f"Advisors already consulted this turn:\n{summary}"}
        )

    return cached_parse(
        model=settings.main_agent_model,
        temperature=settings.decision_temperature,
        messages=messages,
        response_format=RoutingDecision,
    )


def route(
    history: list[dict[str, str]],
    consultations_so_far: list[dict[str, Any]] | None = None,
    last_action: str | None = None,
    qualifying_info_shared: bool = False,
    slots_already_offered: bool = False,
) -> RoutingDecision:
    """Decide the next step from the complete chat history (rule R-2, N-3)."""
    consultations_so_far = consultations_so_far or []
    return get_structured_output(
        lambda: _call_llm(
            history,
            consultations_so_far,
            last_action,
            qualifying_info_shared,
            slots_already_offered,
        ),
        fallback=FALLBACK,
    )
