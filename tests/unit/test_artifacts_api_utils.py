from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api.artifacts import DecisionRecords, discover_runs, normalize_timestamp, resolve_run_dir
from apps.api.main import app


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
