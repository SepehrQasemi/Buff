"""Event-driven risk permission timeline (M4)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_EVENTS_PATH = Path("events") / "events.json"
DEFAULT_FREQ = "1h"

WINDOW_PRE = timedelta(hours=2)
WINDOW_POST = timedelta(hours=2)
HIGH_COOLDOWN = timedelta(hours=4)

SIZE_MULTIPLIER_GREEN = 1.0
SIZE_MULTIPLIER_YELLOW = 0.5
SIZE_MULTIPLIER_RED = 0.0

_FREQ_RE = re.compile(r"^(?P<value>\d+)(?P<unit>[smhd])$")


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


def _ensure_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime."""
    if not isinstance(value, str):
        raise TypeError("timestamp must be a string")
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return _ensure_utc(parsed, "timestamp")


@dataclass(frozen=True)
class Event:
    event_id: str
    ts_utc: datetime
    kind: str
    severity: Severity | str
    source: str
    title: str
    metadata: dict[str, Any] | None = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id is required")
        if not self.kind:
            raise ValueError("kind is required")
        if not self.source:
            raise ValueError("source is required")
        if not self.title:
            raise ValueError("title is required")
        ts_utc = _ensure_utc(self.ts_utc, "ts_utc")
        object.__setattr__(self, "ts_utc", ts_utc)
        severity = self.severity
        if isinstance(severity, str) and not isinstance(severity, Severity):
            try:
                severity = Severity(severity)
            except ValueError as exc:
                raise ValueError("severity must be low, medium, or high") from exc
        if not isinstance(severity, Severity):
            raise ValueError("severity must be low, medium, or high")
        object.__setattr__(self, "severity", severity)
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
        elif not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict if provided")


@dataclass(frozen=True)
class RiskTimelineState:
    ts_utc: datetime
    risk_state: RiskLevel
    size_multiplier: float
    reasons: tuple[str, ...]
    event_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts_utc": self.ts_utc.isoformat(),
            "risk_state": self.risk_state.value,
            "size_multiplier": self.size_multiplier,
            "reasons": list(self.reasons),
            "event_ids": list(self.event_ids),
        }


def event_from_dict(payload: Mapping[str, Any]) -> Event:
    if not isinstance(payload, Mapping):
        raise TypeError("event payload must be a mapping")
    event_id = _require_str(payload, "event_id")
    ts_value = _require_str(payload, "ts_utc")
    kind = _require_str(payload, "kind")
    severity = _require_str(payload, "severity")
    source = _require_str(payload, "source")
    title = _require_str(payload, "title")
    metadata = payload.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a dict if provided")
    return Event(
        event_id=event_id,
        ts_utc=parse_timestamp(ts_value),
        kind=kind,
        severity=severity,
        source=source,
        title=title,
        metadata=dict(metadata),
    )


def load_events_from_json(path: str | Path) -> list[Event]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("events file must contain a list of event objects")
    events = [event_from_dict(item) for item in payload]
    return _sorted_events(events)


def compute_risk_timeline(
    events: Iterable[Event],
    start_ts: datetime,
    end_ts: datetime,
    freq: str = DEFAULT_FREQ,
) -> list[RiskTimelineState]:
    start = _ensure_utc(start_ts, "start_ts")
    end = _ensure_utc(end_ts, "end_ts")
    if end < start:
        raise ValueError("end_ts must be >= start_ts")
    step = _parse_freq(freq)
    sorted_events = _sorted_events(events)
    timeline: list[RiskTimelineState] = []
    current = start
    while current <= end:
        timeline.append(_evaluate_timestamp(current, sorted_events))
        current += step
    return timeline


def write_risk_timeline_json(path: str | Path, timeline: Sequence[RiskTimelineState]) -> Path:
    out_path = Path(path)
    payload = [state.to_dict() for state in timeline]
    content = json.dumps(payload, indent=2, sort_keys=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content + "\n", encoding="utf-8")
    return out_path


def _parse_freq(freq: str) -> timedelta:
    if not isinstance(freq, str):
        raise TypeError("freq must be a string like '1h'")
    match = _FREQ_RE.match(freq.strip().lower())
    if not match:
        raise ValueError("freq must be formatted like '1h', '30m', or '1d'")
    value = int(match.group("value"))
    if value <= 0:
        raise ValueError("freq must be positive")
    unit = match.group("unit")
    if unit == "s":
        return timedelta(seconds=value)
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    return timedelta(days=value)


def _sorted_events(events: Iterable[Event]) -> list[Event]:
    return sorted(events, key=lambda event: (event.ts_utc, event.event_id))


def _evaluate_timestamp(ts_utc: datetime, events: Sequence[Event]) -> RiskTimelineState:
    red_reasons: list[str] = []
    red_ids: list[str] = []
    yellow_reasons: list[str] = []
    yellow_ids: list[str] = []

    for event in events:
        if event.severity == Severity.HIGH:
            if _within_window(ts_utc, event):
                red_reasons.append(_reason("high severity event within window", event))
                red_ids.append(event.event_id)
            elif _in_cooldown(ts_utc, event):
                red_reasons.append(_reason("high severity cooldown after event", event))
                red_ids.append(event.event_id)
        elif event.severity == Severity.MEDIUM:
            if _within_window(ts_utc, event):
                yellow_reasons.append(_reason("medium severity event within window", event))
                yellow_ids.append(event.event_id)

    if red_reasons:
        return RiskTimelineState(
            ts_utc=ts_utc,
            risk_state=RiskLevel.RED,
            size_multiplier=SIZE_MULTIPLIER_RED,
            reasons=tuple(red_reasons),
            event_ids=tuple(red_ids),
        )
    if yellow_reasons:
        return RiskTimelineState(
            ts_utc=ts_utc,
            risk_state=RiskLevel.YELLOW,
            size_multiplier=SIZE_MULTIPLIER_YELLOW,
            reasons=tuple(yellow_reasons),
            event_ids=tuple(yellow_ids),
        )
    return RiskTimelineState(
        ts_utc=ts_utc,
        risk_state=RiskLevel.GREEN,
        size_multiplier=SIZE_MULTIPLIER_GREEN,
        reasons=tuple(),
        event_ids=tuple(),
    )


# DEPRECATED: timeline-local alias retained for compatibility.
RiskState = RiskTimelineState


def _within_window(ts_utc: datetime, event: Event) -> bool:
    return (event.ts_utc - WINDOW_PRE) <= ts_utc <= (event.ts_utc + WINDOW_POST)


def _in_cooldown(ts_utc: datetime, event: Event) -> bool:
    return event.ts_utc < ts_utc <= (event.ts_utc + HIGH_COOLDOWN)


def _reason(prefix: str, event: Event) -> str:
    return f"{prefix}: {event.event_id}"


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
