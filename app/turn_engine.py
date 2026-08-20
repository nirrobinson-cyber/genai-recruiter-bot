"""Turn-engine dispatcher (GRB-041 dual-implementation toggle).

Selects between the original plain-Python turn graph (`app.graph`, the
default) and the LangGraph `StateGraph` implementation
(`app.graph_langgraph`) via `settings.turn_engine`. Both implementations
expose the exact same `run_turn(user_message, state, *, now=None) -> dict`
contract and share the same private synthesis/phase-tracking helpers from
`app.graph`, so switching engines is behavior-preserving by construction.

Callers that just want "the turn graph, whichever one is configured" should
import `run_turn` from here rather than from `app.graph` directly. Callers
that specifically need the legacy implementation (existing tests) keep
importing `app.graph` as before — this module changes nothing about it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.config import get_settings
from app.state import ConversationState


def run_turn(
    user_message: str, state: ConversationState, *, now: datetime | None = None
) -> dict[str, Any]:
    if get_settings().turn_engine == "langgraph":
        from app.graph_langgraph import run_turn as _run_turn

        return _run_turn(user_message, state, now=now)

    from app.graph import run_turn as _run_turn

    return _run_turn(user_message, state, now=now)
