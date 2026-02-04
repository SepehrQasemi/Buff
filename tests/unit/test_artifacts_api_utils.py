from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api.artifacts import DecisionRecords, discover_runs, resolve_run_dir
from apps.api.main import app
from apps.api.timeutils import format_ts, parse_ts


def test_decision_records_malformed_lines(tmp_path):
    decision_path = tmp_path / "decision_records.jsonl"
    decision_path.write_text('{"timestamp": "2026-01-01T00:00:00Z"}\n{not json}\n"string"\n')

    records = DecisionRecords(decision_path)
    payloads = list(records)

    assert len(payloads) == 1
    assert records.malformed_lines == 1


def test_parse_ts_and_format_ts_contract():
    dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    epoch_ms = int(dt.timestamp() * 1000)

    parsed = parse_ts("2026-01-01T00:00:00")
    assert parsed.tzinfo is not None
    assert parsed.isoformat().startswith("2026-01-01T00:00:00")

    parsed = parse_ts("2026-01-01T02:00:00+02:00")
    assert parsed.isoformat().startswith("2026-01-01T00:00:00")

    assert parse_ts(epoch_ms) == dt

    formatted = format_ts(dt)
    assert formatted.endswith("Z")


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


def test_resolve_run_dir_rejects_traversal(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    bad_ids = ["../x", "..\\x", "a/../b", "/abs", "C:\\x", ".hidden", ""]
    for run_id in bad_ids:
        with pytest.raises(HTTPException) as exc:
            resolve_run_dir(run_id, root)
        assert exc.value.status_code == 400


def test_resolve_run_dir_valid_id(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    run_dir = root / "run-123"
    run_dir.mkdir()

    resolved = resolve_run_dir("run-123", root)
    assert resolved == run_dir.resolve()


def test_pagination_rejected(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    run_dir = artifacts_root / "run-123"
    run_dir.mkdir()
    (run_dir / "decision_records.jsonl").write_text("")

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    response = client.get("/api/runs/run-123/decisions", params={"page": 0})
    assert response.status_code == 422

    response = client.get("/api/runs/run-123/decisions", params={"page_size": 1000})
    assert response.status_code == 422


def test_time_range_rejected(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    run_dir = artifacts_root / "run-123"
    run_dir.mkdir()
    (run_dir / "decision_records.jsonl").write_text("")

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    response = client.get(
        "/api/runs/run-123/decisions",
        params={"start_ts": "2026-01-02T00:00:00Z", "end_ts": "2026-01-01T00:00:00Z"},
    )
    assert response.status_code == 400

    response = client.get("/api/runs/run-123/decisions", params={"start_ts": "not-a-date"})
    assert response.status_code == 400

    response = client.get("/api/runs/run-123/decisions", params={"end_ts": "bad"})
    assert response.status_code == 400


def test_timestamp_contract_in_endpoints(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    run_dir = artifacts_root / "run-123"
    run_dir.mkdir()

    dt_epoch = datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc)
    epoch_ms = int(dt_epoch.timestamp() * 1000)

    records = [
        {"timestamp": "2026-01-01T00:00:00Z", "action": "noop"},
        {"timestamp": "2026-01-01T01:00:00", "action": "noop"},
        {"timestamp": "2026-01-01T03:00:00+02:00", "action": "noop"},
        {"timestamp": str(epoch_ms), "action": "noop"},
    ]
    payload = "\n".join([json.dumps(record) for record in records]) + "\n"
    (run_dir / "decision_records.jsonl").write_text(payload)

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    summary = client.get("/api/runs/run-123/summary")
    assert summary.status_code == 200
    summary_data = summary.json()
    assert summary_data["min_timestamp"].endswith("Z")
    assert summary_data["max_timestamp"].endswith("Z")

    decisions = client.get("/api/runs/run-123/decisions")
    assert decisions.status_code == 200
    decisions_data = decisions.json()
    for row in decisions_data["results"]:
        assert row["timestamp"].endswith("Z")

    filtered = client.get(
        "/api/runs/run-123/decisions",
        params={"start_ts": "2026-01-01T00:30:00Z", "end_ts": "2026-01-01T01:30:00Z"},
    )
    assert filtered.status_code == 200
    filtered_data = filtered.json()
    assert len(filtered_data["results"]) == 2
