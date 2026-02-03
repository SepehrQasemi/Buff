from __future__ import annotations

import json
import socket
from pathlib import Path

import pandas as pd

from src.tools import mvp_smoke
from src.data.store import CANONICAL_COLUMNS


def _make_hourly_df(symbol: str, start: str, periods: int) -> pd.DataFrame:
    start_ms = pd.Timestamp(start, tz="UTC").value // 1_000_000
    timestamps = [start_ms + i * 3_600_000 for i in range(periods)]
    base = [100.0 + i for i in range(periods)]
    return pd.DataFrame(
        {
            "symbol": [symbol for _ in range(periods)],
            "timestamp": list(timestamps),
            "open": base,
            "high": [val + 1.0 for val in base],
            "low": [val - 1.0 for val in base],
            "close": [val + 0.5 for val in base],
            "volume": [1000.0 for _ in range(periods)],
        }
    )


def test_mvp_smoke_fast(tmp_path: Path, monkeypatch) -> None:
    periods = 72
    btc = _make_hourly_df("BTCUSDT", "2025-01-01", periods)
    eth = _make_hourly_df("ETHUSDT", "2025-01-01", periods)
    combined = pd.concat([btc, eth], ignore_index=True)

    def fake_download(symbols, start_time, end_time, **kwargs):
        normalized = [sym.strip().upper().replace("/", "") for sym in symbols]
        return combined[combined["symbol"].isin(normalized)].reset_index(drop=True)

    def block_network(*args, **kwargs):
        raise RuntimeError("network disabled in smoke test")

    monkeypatch.setattr(mvp_smoke, "download_ohlcv_1m", fake_download)
    monkeypatch.setattr(socket, "create_connection", block_network)
    monkeypatch.chdir(tmp_path)

    report_path = tmp_path / "reports" / "mvp_smoke.json"
    exit_code = mvp_smoke.main(
        [
            "--symbols",
            "BTCUSDT",
            "ETHUSDT",
            "--timeframe",
            "1h",
            "--since",
            "2025-01-01",
            "--runs",
            "2",
            "--out",
            str(report_path),
        ]
    )

    assert exit_code == 0
    assert report_path.exists()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    for key in [
        "status",
        "params",
        "ingest",
        "reproducibility",
        "validation",
        "features",
        "errors",
        "started_at_utc",
        "finished_at_utc",
    ]:
        assert key in payload

    assert payload["status"] == "pass"
    assert payload["reproducibility"]["stable"] is True
    assert payload["reproducibility"]["hash_type"] == "canonical_csv_sha256"
    assert payload["reproducibility"]["stable_columns"] == list(CANONICAL_COLUMNS)
