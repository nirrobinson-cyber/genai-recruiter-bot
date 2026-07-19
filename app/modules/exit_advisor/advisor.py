"""Exit Advisor (spec §5.2) — decides end / dont_end from the full chat history.

Prompted baseline behind the Strategy interface described in the spec: if
`settings.exit_advisor_finetuned_model` is set, use it; otherwise fall back to
`settings.advisor_model`. No fine-tuned model exists yet (Epic E3).
"""

from __future__ import annotations

from app.config import get_settings
from app.llm_client import cached_parse, history_to_messages
from app.modules.exit_advisor.prompts import SYSTEM_PROMPT
from app.schemas import ExitAdvisorOutput
from app.structured_output import get_structured_output

FALLBACK = ExitAdvisorOutput(
    decision="dont_end",
    confidence=0.0,
    reason="LLM call failed after retry; defaulting to keep the conversation going",
)


def _call_llm(history: list[dict[str, str]], model: str | None = None) -> ExitAdvisorOutput:
    settings = get_settings()
    model = model or settings.exit_advisor_finetuned_model or settings.advisor_model
    return cached_parse(
        model=model,
        temperature=settings.decision_temperature,
        messages=history_to_messages(SYSTEM_PROMPT, history),
        response_format=ExitAdvisorOutput,
    )


def decide(history: list[dict[str, str]], model: str | None = None) -> ExitAdvisorOutput:
    """Decide end/dont_end from the complete chat history (rule R-2, N-3).

    `model` overrides the usual settings-based selection — used by the E3
    baseline comparison (GRB-033) to call the prompted and fine-tuned models
    explicitly, through the same retry/fallback/cache path as production.
    """
    return get_structured_output(lambda: _call_llm(history, model), fallback=FALLBACK)
