from __future__ import annotations

import pytest

from decision_records.schema import SCHEMA_VERSION, validate_decision_record


def _base_record() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": "run1",
        "timestamp_utc": "2026-01-30T00:00:00.000Z",
        "environment": "PAPER",
        "control_status": "ARMED",
        "strategy": {"name": "demo", "version": "1.0.0"},
        "risk_status": "GREEN",
        "execution_status": "EXECUTED",
        "reason": None,
        "inputs_digest": "abc123",
        "artifact_paths": {"decision_records": "workspaces/run1/decision_records.jsonl"},
    }


def test_valid_record_passes() -> None:
    validate_decision_record(_base_record())


def test_missing_required_key_fails() -> None:
    record = _base_record()
    record.pop("run_id")
    with pytest.raises(ValueError):
        validate_decision_record(record)


def test_invalid_enum_fails() -> None:
    record = _base_record()
    record["risk_status"] = "YELLOW"
    with pytest.raises(ValueError):
        validate_decision_record(record)


def test_blocked_requires_reason() -> None:
    record = _base_record()
    record["execution_status"] = "BLOCKED"
    record["reason"] = ""
    with pytest.raises(ValueError):
        validate_decision_record(record)
