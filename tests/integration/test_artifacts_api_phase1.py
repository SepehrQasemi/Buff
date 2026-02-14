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


def _make_artifacts(tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    run_id = "phase1-run"
    run_dir = artifacts_root / run_id
    run_dir.mkdir()

    records = [
        {
            "timestamp": "2026-02-01T00:00:00Z",
            "action": "ENTER_LONG",
            "risk_level": 3,
            "risk_state": "GREEN",
            "permission": "ALLOW",
            "strategy_id": "demo",
            "strategy_version": "1.0",
            "data_snapshot_hash": "snap-001",
            "feature_snapshot_hash": "feat-001",
        },
        {
            "timestamp": "2026-02-01T00:01:00Z",
            "action": "BLOCKED",
            "risk_level": 3,
            "risk_state": "RED",
            "permission": "BLOCK",
            "risk_reason": "max_loss",
            "risk_policy_type": "hard_cap",
        },
    ]
    _write_jsonl(run_dir / "decision_records.jsonl", records)

    trades = pd.DataFrame(
        {
            "ts_utc": ["2026-02-01T00:02:00Z", "2026-02-01T00:03:00Z"],
            "side": ["BUY", "SELL"],
            "price": [101.0, 103.5],
            "pnl": [0.0, 2.5],
            "trade_id": ["t1", "t1"],
        }
    )
    trades.to_parquet(run_dir / "trades.parquet", index=False)

    metrics_payload = {
        "total_return": 0.12,
        "max_drawdown": -0.05,
        "num_trades": 1,
        "win_rate": 1.0,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics_payload), encoding="utf-8")

    ohlcv = pd.DataFrame(
        {
            "ts": pd.date_range("2026-02-01", periods=5, freq="1min", tz="UTC"),
            "open": [100, 101, 102, 101.5, 103],
            "high": [101, 102.5, 103, 103, 104],
            "low": [99.5, 100.5, 101.5, 101, 102],
            "close": [100.5, 102, 102.5, 102.8, 103.5],
            "volume": [12, 9, 11, 15, 10],
        }
    )
    ohlcv.to_parquet(run_dir / "ohlcv_1m.parquet", index=False)

    timeline = [
        {
            "timestamp": "2026-02-01T00:00:00Z",
            "type": "run",
            "title": "start",
            "severity": "INFO",
        }
    ]
    (run_dir / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

    return artifacts_root, run_id


def test_phase1_artifacts_endpoints(monkeypatch, tmp_path):
    artifacts_root, run_id = _make_artifacts(tmp_path)
    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    runs = client.get("/api/v1/runs")
    assert runs.status_code == 200
    payload = runs.json()
    assert payload
    assert payload[0]["id"] == run_id
    assert payload[0]["artifacts"]["metrics"] is True

    summary = client.get(f"/api/v1/runs/{run_id}/summary")
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["run_id"] == run_id
    assert summary_payload["provenance"]["strategy_version"] == "1.0"
    assert summary_payload["risk"]["level"] == 3
    assert summary_payload["risk"]["blocked"] is True

    ohlcv = client.get(f"/api/v1/runs/{run_id}/ohlcv", params={"timeframe": "1m"})
    assert ohlcv.status_code == 200
    ohlcv_payload = ohlcv.json()
    assert ohlcv_payload["count"] == 5
    assert ohlcv_payload["candles"][0]["ts"].endswith("Z")

    markers = client.get(f"/api/v1/runs/{run_id}/trades/markers")
    assert markers.status_code == 200
    markers_payload = markers.json()
    assert markers_payload["total"] == 2
    assert markers_payload["markers"][0]["marker_type"] == "entry"

    metrics = client.get(f"/api/v1/runs/{run_id}/metrics")
    assert metrics.status_code == 200
    metrics_payload = metrics.json()
    assert metrics_payload["total_return"] == 0.12

    timeline = client.get(f"/api/v1/runs/{run_id}/timeline", params={"source": "artifact"})
    assert timeline.status_code == 200
    timeline_payload = timeline.json()
    assert timeline_payload["total"] == 1
    assert timeline_payload["events"][0]["title"] == "start"


def test_phase1_missing_artifacts_root(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "missing"
    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    response = client.get("/api/v1/runs")
    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "artifacts_root_missing"
    assert "path" in payload["details"]


def test_phase1_corrupted_decision_records_fail_closed(monkeypatch, tmp_path):
    artifacts_root, run_id = _make_artifacts(tmp_path)
    decision_path = artifacts_root / run_id / "decision_records.jsonl"
    with decision_path.open("a", encoding="utf-8") as handle:
        handle.write("{bad json}\n")

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    response = client.get(f"/api/v1/runs/{run_id}/summary")
    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "decision_records_invalid"
    assert payload["details"]["malformed_lines_count"] == 1


def test_phase1_missing_trades_and_metrics(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    run_id = "phase1-missing"
    run_dir = artifacts_root / run_id
    run_dir.mkdir()

    _write_jsonl(
        run_dir / "decision_records.jsonl",
        [{"timestamp": "2026-02-01T00:00:00Z", "action": "noop"}],
    )

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    trades = client.get(f"/api/v1/runs/{run_id}/trades")
    assert trades.status_code == 404
    trades_payload = trades.json()
    assert trades_payload["code"] == "trades_missing"

    metrics = client.get(f"/api/v1/runs/{run_id}/metrics")
    assert metrics.status_code == 404
    metrics_payload = metrics.json()
    assert metrics_payload["code"] == "metrics_missing"


def test_phase1_timezone_normalization(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    run_id = "phase1-tz"
    run_dir = artifacts_root / run_id
    run_dir.mkdir()

    records = [
        {"timestamp": "2026-02-01T00:00:00", "action": "noop"},
        {"timestamp": "2026-02-01T02:00:00+02:00", "action": "noop"},
    ]
    _write_jsonl(run_dir / "decision_records.jsonl", records)

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    summary = client.get(f"/api/v1/runs/{run_id}/summary")
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["min_timestamp"].endswith("Z")
    assert summary_payload["max_timestamp"].endswith("Z")
