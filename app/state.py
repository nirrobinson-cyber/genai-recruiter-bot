"""ConversationState schema (spec §12) — state carried across turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ConversationState:
    """Minimal state container for the turn graph."""

    history: list[dict[str, str]] = field(default_factory=list)
    registration_data: dict[str, Any] = field(default_factory=dict)
    advisor_outputs: list[dict[str, Any]] = field(default_factory=list)
    consult_count: int = 0
    now: datetime = field(default_factory=datetime.now)
    # Sticky for the whole conversation once set (spec §5.1 "conversation has
    # matured enough to offer one") — proactive-escalation signal, see app.graph.
    qualifying_info_shared: bool = False

    def add_message(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})
