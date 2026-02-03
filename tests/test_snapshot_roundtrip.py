from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from audit.canonical_json import canonical_json_bytes
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
    expected_hash = sha256(canonical_json_bytes(payload)).hexdigest()
    assert loaded.snapshot_hash == expected_hash
    assert ":" not in loaded.snapshot_hash
    assert out_path.name == loaded.snapshot_ref
    assert out_path.read_text(encoding="utf-8") == loaded.to_canonical_json()


def test_snapshot_hash_canonicalizes_key_order() -> None:
    payload_a = {
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
    payload_b = {
        "selector_inputs": {"trend_state": "up"},
        "config": {"risk_config": {"atr_red": 0.02, "atr_yellow": 0.01, "missing_red": 0.2}},
        "risk_inputs": {
            "invalid_close": False,
            "invalid_index": False,
            "latest_metrics_valid": True,
            "timestamps_valid": True,
            "missing_fraction": 0.0,
            "realized_vol": 0.005,
            "atr_pct": 0.01,
            "as_of": "2026-02-01T00:00:00Z",
            "timeframe": "1m",
            "symbol": "BTCUSDT",
        },
        "features": {"volatility_regime": "low", "trend_state": "up"},
        "market_data": [
            {
                "volume": 10.0,
                "close": 100.5,
                "low": 99.5,
                "high": 101.0,
                "open": 100.0,
                "ts": "2026-02-01T00:00:00Z",
            }
        ],
        "timeframe": "1m",
        "symbol": "BTCUSDT",
        "decision_id": "dec-001",
        "snapshot_version": 1,
    }

    snapshot_a = Snapshot.from_dict(payload_a)
    snapshot_b = Snapshot.from_dict(payload_b)

    assert snapshot_a.snapshot_hash == snapshot_b.snapshot_hash
    assert snapshot_a.snapshot_hash == sha256(canonical_json_bytes(payload_a)).hexdigest()


def test_snapshot_hash_prefix_rejected() -> None:
    payload = {
        "snapshot_version": 1,
        "decision_id": "dec-001",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "market_data": [],
        "features": {},
        "risk_inputs": {},
        "config": {},
        "selector_inputs": {},
        "snapshot_hash": "sha256:deadbeef",
    }

    with pytest.raises(ValueError, match="snapshot_hash does not match"):
        Snapshot.from_dict(payload)
