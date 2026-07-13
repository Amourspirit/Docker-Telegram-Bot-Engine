from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bot_service.result import Result


@dataclass(slots=True)
class EventArgs:
    action_name: str
    user_id: int
    raw_args: tuple[str, ...]
    correlation_id: str
    cancelled: bool = False
    cancel_reason: str | None = None
    shared_state: dict[str, Any] = field(default_factory=dict)
    results: dict[str, Result[Any, BaseException | None]] = field(default_factory=dict)
    response_sections: list[str] = field(default_factory=list)

    def cancel(self, reason: str) -> None:
        self.cancelled = True
        self.cancel_reason = reason

    def add_section(self, section: str) -> None:
        if section:
            self.response_sections.append(section)