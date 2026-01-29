from __future__ import annotations

from pathlib import Path

from audit.decision_records import canonical_json


def write_corrupted_jsonl(path: str) -> None:
    record_a = {
        "schema_version": "dr.v1",
        "run_id": "test_run",
        "seq": 0,
        "ts_utc": "2026-01-01T00:00:00.000Z",
        "timeframe": "1m",
        "risk_state": "GREEN",
        "market_state": {"trend_state": "UP"},
        "market_state_hash": "sha256:dummy",
        "selection": {"strategy_id": "trend_follow_v1_conservative", "engine_id": "trend", "reason": []},
    }
    record_b = {
        "schema_version": "dr.v1",
        "run_id": "test_run",
        "seq": 1,
        "ts_utc": "2026-01-01T00:00:01.000Z",
        "timeframe": "1m",
        "risk_state": "GREEN",
        "market_state": {"trend_state": "DOWN"},
        "market_state_hash": "sha256:dummy",
        "selection": {"strategy_id": "trend_follow_v1_short", "engine_id": "trend", "reason": []},
    }
    lines = [
        canonical_json(record_a),
        "{bad json",
        canonical_json(record_b),
        "{\"schema_version\": \"dr.v1\"",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def truncate_file_mid_line(path: str) -> None:
    file_path = Path(path)
    data = file_path.read_bytes()
    if len(data) < 5:
        return
    file_path.write_bytes(data[:-5])


def append_valid_record_line(path: str, record: dict) -> None:
    file_path = Path(path)
    with file_path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(record))
        handle.write("\n")
