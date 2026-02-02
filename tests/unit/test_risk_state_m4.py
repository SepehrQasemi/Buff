from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from risk.risk_state import (
    HIGH_COOLDOWN,
    SIZE_MULTIPLIER_GREEN,
    SIZE_MULTIPLIER_RED,
    WINDOW_POST,
    WINDOW_PRE,
    Event,
    RiskLevel,
    compute_risk_timeline,
    load_events_from_json,
    write_risk_timeline_json,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "risk_events.json"


def _timeline_hash(timeline: list) -> str:
    payload = [state.to_dict() for state in timeline]
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(text.encode("utf-8")).hexdigest()


def test_determinism_timeline_and_json(tmp_path: Path) -> None:
    events = load_events_from_json(FIXTURE_PATH)
    start = datetime(2026, 1, 10, 8, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 10, 20, 0, tzinfo=timezone.utc)

    timeline_a = compute_risk_timeline(events, start, end, freq="1h")
    timeline_b = compute_risk_timeline(list(reversed(events)), start, end, freq="1h")

    assert _timeline_hash(timeline_a) == _timeline_hash(timeline_b)

    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    write_risk_timeline_json(out_a, timeline_a)
    write_risk_timeline_json(out_b, timeline_b)
    assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")


def test_explainability_reasons_and_event_ids() -> None:
    event_ts = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
    events = [
        Event(
            event_id="evt_high_1",
            ts_utc=event_ts,
            kind="macro",
            severity="high",
            source="calendar",
            title="Macro release",
        ),
        Event(
            event_id="evt_med_1",
            ts_utc=event_ts + timedelta(hours=1),
            kind="earnings",
            severity="medium",
            source="calendar",
            title="Earnings update",
        ),
    ]

    start = event_ts - WINDOW_PRE
    end = event_ts + WINDOW_POST
    timeline = compute_risk_timeline(events, start, end, freq="1h")

    assert any(state.risk_state != RiskLevel.GREEN for state in timeline)
    for state in timeline:
        if state.risk_state != RiskLevel.GREEN:
            assert state.reasons
            assert state.event_ids


def test_window_logic_medium_event() -> None:
    event_ts = datetime(2026, 1, 6, 10, 0, tzinfo=timezone.utc)
    event = Event(
        event_id="evt_med_window",
        ts_utc=event_ts,
        kind="macro",
        severity="medium",
        source="calendar",
        title="Medium severity window",
    )

    outside = event_ts - WINDOW_PRE - timedelta(minutes=1)
    state = compute_risk_timeline([event], outside, outside, freq="1h")[0]
    assert state.risk_state == RiskLevel.GREEN

    inside = event_ts - WINDOW_PRE
    state = compute_risk_timeline([event], inside, inside, freq="1h")[0]
    assert state.risk_state == RiskLevel.YELLOW
    assert any("within window" in reason for reason in state.reasons)


def test_window_logic_high_cooldown() -> None:
    event_ts = datetime(2026, 1, 7, 9, 0, tzinfo=timezone.utc)
    event = Event(
        event_id="evt_high_cooldown",
        ts_utc=event_ts,
        kind="geo",
        severity="high",
        source="headlines",
        title="High severity event",
    )

    assert HIGH_COOLDOWN > WINDOW_POST
    cooldown_time = event_ts + WINDOW_POST + timedelta(minutes=1)
    state = compute_risk_timeline([event], cooldown_time, cooldown_time, freq="1h")[0]
    assert state.risk_state == RiskLevel.RED
    assert any("cooldown" in reason for reason in state.reasons)

    after_cooldown = event_ts + HIGH_COOLDOWN + timedelta(minutes=1)
    state = compute_risk_timeline([event], after_cooldown, after_cooldown, freq="1h")[0]
    assert state.risk_state == RiskLevel.GREEN


def test_permission_only_output_and_multiplier() -> None:
    events = load_events_from_json(FIXTURE_PATH)
    start = datetime(2026, 1, 10, 8, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 10, 20, 0, tzinfo=timezone.utc)
    timeline = compute_risk_timeline(events, start, end, freq="1h")

    forbidden = {"buy", "sell", "long", "short", "signal", "entry", "exit", "strategy", "position"}

    for state in timeline:
        payload = state.to_dict()
        for key, value in payload.items():
            _assert_no_forbidden(str(key), forbidden)
            _check_value_forbidden(value, forbidden)
        if state.risk_state == RiskLevel.GREEN:
            assert state.size_multiplier == SIZE_MULTIPLIER_GREEN
        elif state.risk_state == RiskLevel.RED:
            assert state.size_multiplier == SIZE_MULTIPLIER_RED
        else:
            assert 0.0 < state.size_multiplier < 1.0


def _check_value_forbidden(value: object, forbidden: set[str]) -> None:
    if isinstance(value, str):
        _assert_no_forbidden(value, forbidden)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                _assert_no_forbidden(item, forbidden)


def _assert_no_forbidden(text: str, forbidden: set[str]) -> None:
    lowered = text.lower()
    for term in forbidden:
        assert term not in lowered
