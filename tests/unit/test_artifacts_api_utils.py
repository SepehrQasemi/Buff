from __future__ import annotations

from datetime import datetime, timezone

from apps.api.artifacts import DecisionRecords, discover_runs, normalize_timestamp


def test_decision_records_malformed_lines(tmp_path):
    decision_path = tmp_path / "decision_records.jsonl"
    decision_path.write_text('{"timestamp": "2026-01-01T00:00:00Z"}\n{not json}\n"string"\n')

    records = DecisionRecords(decision_path)
    payloads = list(records)

    assert len(payloads) == 1
    assert records.malformed_lines == 1


def test_normalize_timestamp_epoch_and_iso():
    dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    epoch_ms = int(dt.timestamp() * 1000)

    assert normalize_timestamp("2026-01-01T00:00:00Z") == dt.isoformat()
    assert normalize_timestamp(epoch_ms) == dt.isoformat()


def test_discover_runs_marks_invalid_and_sorts(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    valid_run = artifacts_root / "run_ok"
    invalid_run = artifacts_root / "run_invalid"
    valid_run.mkdir()
    invalid_run.mkdir()

    decision_path = valid_run / "decision_records.jsonl"
    decision_path.write_text('{"timestamp": "2026-01-01T00:00:00Z"}\n')

    older_time = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    newer_time = datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp()

    import os

    os.utime(decision_path, (older_time, older_time))
    os.utime(invalid_run, (newer_time, newer_time))

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))

    runs = discover_runs()

    assert len(runs) == 2
    assert runs[0]["id"] == "run_invalid"
    assert runs[0]["status"] == "INVALID"
    assert runs[1]["status"] == "OK"
