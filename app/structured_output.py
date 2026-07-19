"""Structured-output parsing with retry/fallback (GRB-020, rule N-3).

Every LLM decision must be parsed via a Pydantic schema; on parse failure,
retry once, then fall back to a deterministic default. This helper is kept
independent of any specific LLM client so advisors can inject whatever call
produces their schema instance, and so it is unit-testable without real API
calls.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


def get_structured_output(call: Callable[[], T], fallback: T) -> T:
    """Call `call()` up to twice; return `fallback` if both attempts fail."""

    for attempt in range(2):
        try:
            return call()
        except Exception:
            logger.warning("structured output attempt %d failed", attempt + 1, exc_info=True)
    return fallback
