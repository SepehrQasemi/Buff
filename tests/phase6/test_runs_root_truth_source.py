from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.phase6.paths import user_root, user_runs_root
from apps.api.phase6.registry import upsert_registry_entry

TEST_USER_ID = "test-user"


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def _make_runs_root_run(runs_root: Path, run_id: str) -> Path:
    run_dir = user_runs_root(runs_root, TEST_USER_ID) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    records = [
        {"timestamp": "2026-02-01T00:00:00Z", "action": "ENTER_LONG", "symbol": "BTCUSDT"},
        {"timestamp": "2026-02-01T00:01:00Z", "action": "EXIT_LONG", "symbol": "BTCUSDT"},
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
    _write_jsonl(
        run_dir / "trades.jsonl",
        [
            {"timestamp": "2026-02-01T00:02:00Z", "price": 101.0, "side": "BUY"},
            {"timestamp": "2026-02-01T00:03:00Z", "price": 103.5, "side": "SELL"},
        ],
    )

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

    metrics_payload = {
        "total_return": 0.12,
        "max_drawdown": -0.05,
        "num_trades": 1,
        "win_rate": 1.0,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics_payload), encoding="utf-8")

    config_payload = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "engine_version": "phase6-1.0.0",
    }
    (run_dir / "config.json").write_text(json.dumps(config_payload), encoding="utf-8")

    equity_curve = [{"timestamp": "2026-02-01T00:00:00Z", "equity": 10000.0}]
    (run_dir / "equity_curve.json").write_text(json.dumps(equity_curve), encoding="utf-8")

    timeline = [{"timestamp": "2026-02-01T00:00:00Z", "type": "INFO", "title": "Run created"}]
    (run_dir / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

    manifest = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "created_at": "2026-02-01T00:00:00Z",
        "inputs_hash": "hash-demo",
        "status": "COMPLETED",
        "data": {"symbol": "BTCUSDT", "timeframe": "1m"},
        "strategy": {"id": "hold"},
        "meta": {"owner_user_id": TEST_USER_ID},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    upsert_registry_entry(user_root(runs_root, TEST_USER_ID), run_dir, manifest)
    return run_dir


def _make_demo_artifacts(artifacts_root: Path, run_id: str) -> Path:
    run_dir = artifacts_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(run_dir / "decision_records.jsonl", [{"timestamp": "2026-02-01T00:00:00Z"}])
    return run_dir


def test_runs_root_unset_returns_error(monkeypatch):
    monkeypatch.delenv("RUNS_ROOT", raising=False)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    client = TestClient(app)

    response = client.get("/api/v1/runs")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "RUNS_ROOT_UNSET"


def test_runs_root_detail_endpoints_use_registry(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    run_id = "run-truth"
    _make_runs_root_run(runs_root, run_id)

    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    monkeypatch.delenv("DEMO_MODE", raising=False)

    client = TestClient(app)

    runs = client.get("/api/v1/runs")
    assert runs.status_code == 200
    runs_data = runs.json()
    assert any(item.get("run_id") == run_id for item in runs_data)

    summary = client.get(f"/api/v1/runs/{run_id}/summary")
    assert summary.status_code == 200
    assert summary.json().get("mode") is None

    trades = client.get(f"/api/v1/runs/{run_id}/trades")
    assert trades.status_code == 200
    assert trades.json().get("mode") is None

    metrics = client.get(f"/api/v1/runs/{run_id}/metrics")
    assert metrics.status_code == 200
    assert metrics.json().get("mode") is None

    ohlcv = client.get(f"/api/v1/runs/{run_id}/ohlcv", params={"timeframe": "1m"})
    assert ohlcv.status_code == 200
    assert ohlcv.json().get("mode") is None

    timeline = client.get(f"/api/v1/runs/{run_id}/timeline", params={"source": "artifact"})
    assert timeline.status_code == 200
    assert timeline.json().get("mode") is None


def test_demo_mode_allows_artifacts_root(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    run_id = "run-demo"
    _make_demo_artifacts(artifacts_root, run_id)

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    monkeypatch.delenv("RUNS_ROOT", raising=False)
    monkeypatch.setenv("DEMO_MODE", "1")

    client = TestClient(app)

    runs = client.get("/api/v1/runs")
    assert runs.status_code == 200
    runs_data = runs.json()
    assert any(item.get("id") == run_id for item in runs_data)
    assert all(item.get("mode") == "demo" for item in runs_data if isinstance(item, dict))

    summary = client.get(f"/api/v1/runs/{run_id}/summary")
    assert summary.status_code == 200
    assert summary.json().get("mode") == "demo"
