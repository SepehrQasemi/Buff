import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app


@pytest.fixture(autouse=True)
def _enable_demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.delenv("RUNS_ROOT", raising=False)


def _write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def test_artifacts_api_smoke_ui_contract(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    run_id = "run-ui"
    run_dir = artifacts_root / run_id
    run_dir.mkdir()

    epoch_ms = int(datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc).timestamp() * 1000)
    records = [
        {"timestamp": "2026-01-01T00:00:00Z", "action": "noop", "severity": "INFO"},
        {"timestamp": "2026-01-01T01:00:00", "action": "placed", "severity": "INFO"},
        {"timestamp": epoch_ms, "action": "blocked", "severity": "ERROR"},
    ]

    decision_path = run_dir / "decision_records.jsonl"
    _write_jsonl(decision_path, records)

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    health_data = health.json()
    assert health_data["status"] == "ok"
    assert health_data["api_version"] == "1"

    health_v1 = client.get("/api/v1/health")
    assert health_v1.status_code == 200
    assert health_v1.json()["api_version"] == "1"

    runs = client.get("/api/runs")
    assert runs.status_code == 200
    runs_data = runs.json()
    assert any(item["id"] == run_id for item in runs_data)

    summary = client.get(f"/api/runs/{run_id}/summary")
    assert summary.status_code == 200
    summary_data = summary.json()
    assert summary_data["min_timestamp"].endswith("Z")
    assert summary_data["max_timestamp"].endswith("Z")
    assert summary_data["malformed_lines_count"] == 0

    decisions = client.get(f"/api/runs/{run_id}/decisions", params={"page": 1, "page_size": 2})
    assert decisions.status_code == 200
    decisions_data = decisions.json()
    assert decisions_data["total"] == 3
    assert len(decisions_data["results"]) == 2
    for item in decisions_data["results"]:
        assert item["timestamp"].endswith("Z")

    errors = client.get(f"/api/runs/{run_id}/errors")
    assert errors.status_code == 200
    errors_data = errors.json()
    assert errors_data["total_errors"] == 1
    assert errors_data["errors"]
