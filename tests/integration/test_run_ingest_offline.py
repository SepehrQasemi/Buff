"""Integration tests for run_ingest with offline fake data."""

import json

import pandas as pd
import pytest

from buff.data.report import build_report, write_report
from buff.data.store import load_parquet, ohlcv_parquet_path, save_parquet


pytestmark = pytest.mark.integration


def test_run_ingest_creates_parquet_and_report(tmp_path, monkeypatch):
    """Report JSON has expected schema after parquet creation."""
    monkeypatch.chdir(tmp_path)

    data_dir = tmp_path / "data" / "ohlcv"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "ts": pd.date_range("2023-01-01", periods=10, freq="1min", tz="UTC"),
            "open": [100.0 + i for i in range(10)],
            "high": [101.0 + i for i in range(10)],
            "low": [99.0 + i for i in range(10)],
            "close": [100.5 + i for i in range(10)],
            "volume": [1000.0] * 10,
        }
    )

    filepath = ohlcv_parquet_path(data_dir, "BTC/USDT", "1m")
    save_parquet(df, str(filepath))

    report = build_report(data_dir, ["BTC/USDT"], ["1m"], strict=False)
    report_path = reports_dir / "data_quality.json"
    write_report(report, report_path)

    assert filepath.exists()
    assert report_path.exists()

    report_loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert "per_symbol" in report_loaded
    assert isinstance(report_loaded["per_symbol"], list)
    assert report_loaded["per_symbol"][0]["symbol"] == "BTC/USDT"


def test_parquet_has_utc_timestamps(tmp_path):
    """Parquet file contains UTC-aware datetime column."""
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2023-01-01", periods=50, freq="1min", tz="UTC"),
            "open": [100.0] * 50,
            "high": [101.0] * 50,
            "low": [99.0] * 50,
            "close": [100.5] * 50,
            "volume": [1000.0] * 50,
        }
    )

    parquet_path = tmp_path / "test.parquet"
    save_parquet(df, str(parquet_path))

    loaded = load_parquet(str(parquet_path))

    assert "ts" in loaded.columns
    assert pd.api.types.is_datetime64tz_dtype(loaded["ts"])
    assert loaded["ts"].is_monotonic_increasing


def test_report_json_is_valid(tmp_path):
    """Report JSON can be parsed and has correct types."""
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2023-01-01", periods=10, freq="1min", tz="UTC"),
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.5] * 10,
            "volume": [1000.0] * 10,
        }
    )

    data_dir = tmp_path / "data" / "ohlcv"
    filepath = ohlcv_parquet_path(data_dir, "BTC/USDT", "1m")
    save_parquet(df, str(filepath))

    report = build_report(data_dir, ["BTC/USDT"], ["1m"], strict=False)
    report_path = tmp_path / "test_report.json"
    write_report(report, report_path)

    loaded = json.loads(report_path.read_text(encoding="utf-8"))

    assert loaded["per_symbol"][0]["rows_total"] == 10
    assert isinstance(loaded["per_symbol"][0]["gap_ranges"], list)
