from __future__ import annotations

from pathlib import Path

from audit.snapshot import Snapshot, create_snapshot, load_snapshot


def test_snapshot_roundtrip(tmp_path: Path) -> None:
    payload = {
        "snapshot_version": 1,
        "decision_id": "dec-001",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "market_data": [
            {
                "ts": "2026-02-01T00:00:00Z",
                "open": 100.0,
                "high": 101.0,
                "low": 99.5,
                "close": 100.5,
                "volume": 10.0,
            }
        ],
        "features": {"trend_state": "up", "volatility_regime": "low"},
        "risk_inputs": {
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "as_of": "2026-02-01T00:00:00Z",
            "atr_pct": 0.01,
            "realized_vol": 0.005,
            "missing_fraction": 0.0,
            "timestamps_valid": True,
            "latest_metrics_valid": True,
            "invalid_index": False,
            "invalid_close": False,
        },
        "config": {"risk_config": {"missing_red": 0.2, "atr_yellow": 0.01, "atr_red": 0.02}},
        "selector_inputs": {"trend_state": "up"},
    }

    out_path = create_snapshot(payload, tmp_path)
    loaded = load_snapshot(out_path)

    assert isinstance(loaded, Snapshot)
    assert loaded.snapshot_hash is not None
    assert out_path.name == loaded.snapshot_ref
    assert out_path.read_text(encoding="utf-8") == loaded.to_canonical_json()
