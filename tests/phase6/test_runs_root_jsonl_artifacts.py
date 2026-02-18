from __future__ import annotations

import json
from pathlib import Path

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


def _make_jsonl_run(runs_root: Path, run_id: str) -> Path:
    run_dir = user_runs_root(runs_root, TEST_USER_ID) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(
        run_dir / "decision_records.jsonl",
        [
            {"timestamp": "2026-02-01T00:00:00Z", "action": "ENTER_LONG"},
            {"timestamp": "2026-02-01T00:01:00Z", "action": "EXIT_LONG"},
        ],
    )

    _write_jsonl(
        run_dir / "trades.jsonl",
        [
            {
                "entry_time": "2026-02-01T00:00:00Z",
                "exit_time": "2026-02-01T00:02:00Z",
                "entry_price": 100.0,
                "exit_price": 101.2,
                "qty": 1.0,
                "pnl": 1.2,
                "fees": 0.0,
                "side": "LONG",
            },
            {
                "entry_time": "2026-02-01T00:03:00Z",
                "exit_time": "2026-02-01T00:04:00Z",
                "entry_price": 101.2,
                "exit_price": 100.8,
                "qty": 1.0,
                "pnl": -0.4,
                "fees": 0.0,
                "side": "SHORT",
            },
        ],
    )

    _write_jsonl(
        run_dir / "ohlcv_1m.jsonl",
        [
            {
                "ts": "2026-02-01T00:00:00Z",
                "open": 100.0,
                "high": 101.0,
                "low": 99.5,
                "close": 100.5,
                "volume": 10.0,
            },
            {
                "ts": "2026-02-01T00:01:00Z",
                "open": 100.5,
                "high": 101.2,
                "low": 100.0,
                "close": 101.0,
                "volume": 12.0,
            },
            {
                "ts": "2026-02-01T00:02:00Z",
                "open": 101.0,
                "high": 101.5,
                "low": 100.6,
                "close": 101.2,
                "volume": 9.0,
            },
        ],
    )

    metrics_payload = {
        "costs": {"commission_bps": 0.0, "slippage_bps": 0.0},
        "final_equity": 10078.0,
        "initial_equity": 10000.0,
        "max_drawdown": 0.0,
        "num_records": 2,
        "risk_level": 3,
        "strategy_id": "hold",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "total_return": 0.0078,
        "win_rate": 1.0,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics_payload), encoding="utf-8")

    config_payload = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "engine_version": "phase6-1.0.0",
    }
    (run_dir / "config.json").write_text(json.dumps(config_payload), encoding="utf-8")

    equity_curve = [
        {"timestamp": "2026-02-01T00:00:00Z", "equity": 10000.0},
        {"timestamp": "2026-02-01T00:02:00Z", "equity": 10078.0},
    ]
    (run_dir / "equity_curve.json").write_text(json.dumps(equity_curve), encoding="utf-8")

    timeline = [
        {
            "timestamp": "2026-02-01T00:00:00Z",
            "type": "run",
            "title": "start",
            "severity": "INFO",
        }
    ]
    (run_dir / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

    manifest = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "created_at": "2026-02-01T00:00:00Z",
        "inputs_hash": "hash-jsonl",
        "status": "COMPLETED",
        "data": {"symbol": "BTCUSDT", "timeframe": "1m"},
        "strategy": {"id": "hold"},
        "meta": {"owner_user_id": TEST_USER_ID},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    upsert_registry_entry(user_root(runs_root, TEST_USER_ID), run_dir, manifest)
    return run_dir


def test_runs_root_jsonl_artifacts(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    run_id = "run-jsonl"
    _make_jsonl_run(runs_root, run_id)

    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("ARTIFACTS_ROOT", raising=False)

    client = TestClient(app)

    trades = client.get(f"/api/v1/runs/{run_id}/trades")
    assert trades.status_code == 200
    trades_payload = trades.json()
    assert trades_payload["total"] == 2
    assert trades_payload["timestamp_field"] == "timestamp"
    assert trades_payload["results"][0]["price"] is not None

    trades_export = client.get(
        f"/api/v1/runs/{run_id}/trades/export",
        params={"format": "json"},
    )
    assert trades_export.status_code == 200
    export_payload = json.loads(trades_export.text)
    assert len(export_payload) == 2
    assert export_payload[0]["timestamp"].endswith("Z")

    markers = client.get(f"/api/v1/runs/{run_id}/trades/markers")
    assert markers.status_code == 200
    markers_payload = markers.json()
    assert markers_payload["total"] >= 2
    assert markers_payload["markers"][0]["marker_type"] in {"entry", "exit", "event"}

    ohlcv = client.get(f"/api/v1/runs/{run_id}/ohlcv", params={"timeframe": "1m"})
    assert ohlcv.status_code == 200
    ohlcv_payload = ohlcv.json()
    assert ohlcv_payload["count"] == 3
    assert ohlcv_payload["candles"][0]["ts"].endswith("Z")
    assert ohlcv_payload["source"].endswith(".jsonl")

    metrics = client.get(f"/api/v1/runs/{run_id}/metrics")
    assert metrics.status_code == 200
    metrics_payload = metrics.json()
    assert metrics_payload["num_records"] == 2

    timeline = client.get(f"/api/v1/runs/{run_id}/timeline", params={"source": "artifact"})
    assert timeline.status_code == 200
    timeline_payload = timeline.json()
    assert timeline_payload["total"] == 1
    assert timeline_payload["events"][0]["title"] == "start"

    summary = client.get(f"/api/v1/runs/{run_id}/summary")
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["run_id"] == run_id
    assert summary_payload["artifacts"]["trades"] is True
    assert summary_payload["artifacts"]["ohlcv"] is True
    assert summary_payload["artifacts"]["metrics"] is True
    assert summary_payload["artifacts"]["timeline"] is True
