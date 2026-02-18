import json

import pandas as pd
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


def test_export_endpoints(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    run_id = "run-export"
    run_dir = artifacts_root / run_id
    run_dir.mkdir()

    records = [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "action": "placed",
            "symbol": "BTCUSDT",
            "message": '=HYPERLINK("http://evil")',
        },
        {"timestamp": "2026-01-01T01:00:00", "action": "noop", "symbol": "ETHUSDT"},
        {"timestamp": "2026-01-01T02:00:00Z", "action": "placed", "symbol": "BTCUSDT"},
        {"timestamp": "2026-01-01T03:00:00Z", "action": "blocked", "severity": "ERROR"},
    ]
    _write_jsonl(run_dir / "decision_records.jsonl", records)

    trades = pd.DataFrame(
        {
            "timestamp": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T01:00:00Z",
            ],
            "pnl": [1.0, -0.5],
        }
    )
    trades.to_parquet(run_dir / "trades.parquet", index=False)

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    decisions = client.get(
        f"/api/runs/{run_id}/decisions/export",
        params={"format": "json", "symbol": "BTCUSDT"},
    )
    assert decisions.status_code == 200
    assert decisions.headers["content-type"].startswith("application/json")
    assert "attachment" in decisions.headers["content-disposition"]
    assert "run-export-decisions.json" in decisions.headers["content-disposition"]
    decisions_data = json.loads(decisions.text)
    assert len(decisions_data) == 2
    assert all(item["symbol"] == "BTCUSDT" for item in decisions_data)
    assert all(item["timestamp"].endswith("Z") for item in decisions_data)
    assert decisions.headers["cache-control"] == "no-store"

    errors_csv = client.get(f"/api/runs/{run_id}/errors/export", params={"format": "csv"})
    assert errors_csv.status_code == 200
    assert errors_csv.headers["content-type"].startswith("text/csv")
    assert "attachment" in errors_csv.headers["content-disposition"]
    assert "run-export-errors.csv" in errors_csv.headers["content-disposition"]
    assert errors_csv.headers["cache-control"] == "no-store"
    lines = errors_csv.text.strip().splitlines()
    assert len(lines) >= 2
    header = lines[0].split(",")
    assert "timestamp" in header
    ts_index = header.index("timestamp")
    assert lines[1].split(",")[ts_index].endswith("Z")

    trades_json = client.get(f"/api/runs/{run_id}/trades/export", params={"format": "json"})
    assert trades_json.status_code == 200
    assert "run-export-trades.json" in trades_json.headers["content-disposition"]
    trades_data = json.loads(trades_json.text)
    assert len(trades_data) == 2
    assert all(item["timestamp"].endswith("Z") for item in trades_data)
    assert trades_json.headers["cache-control"] == "no-store"

    decisions_csv = client.get(
        f"/api/runs/{run_id}/decisions/export", params={"format": "csv", "symbol": "BTCUSDT"}
    )
    assert decisions_csv.status_code == 200
    import csv

    csv_lines = decisions_csv.text.strip().splitlines()
    reader = csv.reader(csv_lines)
    header = next(reader)
    message_index = header.index("message")
    first_row = next(reader)
    assert first_row[message_index].startswith("'=")

    ndjson = client.get(
        f"/api/runs/{run_id}/decisions/export", params={"format": "ndjson", "symbol": "BTCUSDT"}
    )
    assert ndjson.status_code == 200
    assert ndjson.headers["content-type"].startswith("application/x-ndjson")
    assert "run-export-decisions.ndjson" in ndjson.headers["content-disposition"]
    ndjson_lines = [line for line in ndjson.text.strip().splitlines() if line]
    assert len(ndjson_lines) == 2
    for line in ndjson_lines:
        assert json.loads(line)["timestamp"].endswith("Z")

    invalid = client.get("/api/runs/.hidden/decisions/export", params={"format": "json"})
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "RUN_ID_INVALID"

    trimmed = client.get(
        f"/api/runs/{run_id}/decisions",
        params={"symbol": "BTCUSDT, ,ETHUSDT", "page_size": 10},
    )
    assert trimmed.status_code == 200
    assert trimmed.json()["total"] == 3

    over_limit = ",".join([f"S{i}" for i in range(51)])
    too_many = client.get(
        f"/api/runs/{run_id}/decisions/export", params={"format": "json", "symbol": over_limit}
    )
    assert too_many.status_code == 400
    assert too_many.json()["code"] == "too_many_filter_values"
