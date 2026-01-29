from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IdempotencyStore:
    """In-memory idempotency store."""

    seen_event_ids: set[str] = field(default_factory=set)

    def seen(self, event_id: str) -> bool:
        return event_id in self.seen_event_ids

    def mark(self, event_id: str) -> None:
        self.seen_event_ids.add(event_id)
