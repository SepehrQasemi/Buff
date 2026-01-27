"""Integration tests for run_ingest with offline fake data."""

import json
from pathlib import Path

import pandas as pd
import pytest

from buff.data.report import build_report, write_report
from buff.data.store import save_parquet, symbol_to_filename, load_parquet


pytestmark = pytest.mark.integration


@pytest.fixture
def fake_fetch_ohlcv():
    """Fixture: fake fetch_ohlcv that returns deterministic data."""
    def _fetch(symbol, timeframe, since_ms, limit):
        """Return 100 deterministic hourly candles."""
        candles = []
        for i in range(100):
            ts_ms = since_ms + (i * 3600000)
            candles.append([
                ts_ms,
                100.0 + i,
                101.0 + i,
                99.0 + i,
                100.5 + i,
                1000.0 + (100 if i % 10 == 5 else 0),
            ])
        return candles

    return _fetch


def test_run_ingest_creates_parquet_and_report(tmp_path, monkeypatch):
    """Report JSON has expected schema after parquet creation."""
    monkeypatch.chdir(tmp_path)

    data_dir = tmp_path / "data" / "clean"
    reports_dir = tmp_path / "reports"
    data_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame({
        "ts": pd.date_range("2023-01-01", periods=100, freq="h", tz="UTC"),
        "open": [100.0 + i for i in range(100)],
        "high": [101.0 + i for i in range(100)],
        "low": [99.0 + i for i in range(100)],
        "close": [100.5 + i for i in range(100)],
        "volume": [1000.0] * 100,
    })

    filename = symbol_to_filename("BTC/USDT", "1h")
    filepath = data_dir / filename
    save_parquet(df, str(filepath))

    report = build_report(data_dir, ["BTC/USDT"], "1h", strict=False)
    report_path = reports_dir / "data_quality.json"
    write_report(report, report_path)

    assert (data_dir / "BTC_USDT_1h.parquet").exists()
    assert report_path.exists()

    with open(report_path) as f:
        report_loaded = json.load(f)

    assert "per_symbol" in report_loaded
    assert isinstance(report_loaded["per_symbol"], list)
    assert report_loaded["per_symbol"][0]["symbol"] == "BTC/USDT"


def test_parquet_has_utc_timestamps(tmp_path):
    """Parquet file contains UTC-aware datetime column."""
    df = pd.DataFrame({
        "ts": pd.date_range("2023-01-01", periods=50, freq="h", tz="UTC"),
        "open": [100.0] * 50,
        "high": [101.0] * 50,
        "low": [99.0] * 50,
        "close": [100.5] * 50,
        "volume": [1000.0] * 50,
    })

    parquet_path = tmp_path / "test.parquet"
    save_parquet(df, str(parquet_path))

    loaded = load_parquet(str(parquet_path))

    assert "ts" in loaded.columns
    assert pd.api.types.is_datetime64tz_dtype(loaded["ts"])
    assert loaded["ts"].is_monotonic_increasing


def test_report_json_is_valid(tmp_path):
    """Report JSON can be parsed and has correct types."""
    df = pd.DataFrame({
        "ts": pd.date_range("2023-01-01", periods=10, freq="h", tz="UTC"),
        "open": [100.0] * 10,
        "high": [101.0] * 10,
        "low": [99.0] * 10,
        "close": [100.5] * 10,
        "volume": [1000.0] * 10,
    })

    data_dir = tmp_path / "data" / "clean"
    data_dir.mkdir(parents=True, exist_ok=True)
    filename = symbol_to_filename("BTC/USDT", "1h")
    save_parquet(df, str(data_dir / filename))

    report = build_report(data_dir, ["BTC/USDT"], "1h", strict=False)
    report_path = tmp_path / "test_report.json"
    write_report(report, report_path)

    with open(report_path) as f:
        loaded = json.load(f)

    assert loaded["per_symbol"][0]["rows_total"] == 10
    assert isinstance(loaded["per_symbol"][0]["gap_ranges"], list)
