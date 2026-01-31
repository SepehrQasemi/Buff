from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now_utc(self) -> datetime: ...


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    ts = value.astimezone(timezone.utc).isoformat(timespec="seconds")
    return ts.replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    ts = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(ts)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
