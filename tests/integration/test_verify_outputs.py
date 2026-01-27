"""Integration tests for verify_outputs with offline data."""

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from buff.data.report import build_report, write_report
from buff.data.store import save_parquet, symbol_to_filename


pytestmark = pytest.mark.integration


def create_test_parquet_and_report(tmp_path, symbol="BTC/USDT", rows=100):
    """Helper: create a parquet and report for testing."""
    df = pd.DataFrame({
        "ts": pd.date_range("2023-01-01", periods=rows, freq="h", tz="UTC"),
        "open": [100.0] * rows,
        "high": [101.0] * rows,
        "low": [99.0] * rows,
        "close": [100.5] * rows,
        "volume": [1000.0] * rows,
    })

    data_dir = tmp_path / "data" / "clean"
    data_dir.mkdir(parents=True, exist_ok=True)
    filename = symbol_to_filename(symbol, "1h")
    filepath = data_dir / filename
    save_parquet(df, str(filepath))

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(data_dir, [symbol], "1h", strict=False)
    report_path = reports_dir / "data_quality.json"
    write_report(report, report_path)

    return df, report


def test_verify_outputs_pass_correct_data(tmp_path, monkeypatch):
    """verify_outputs passes when data and report match."""
    monkeypatch.chdir(tmp_path)

    create_test_parquet_and_report(tmp_path, "BTC/USDT", rows=50)

    from buff.data import verify_outputs as verify_module
    outputs = []

    def capture_print(*args, **kwargs):
        outputs.append(" ".join(str(arg) for arg in args))

    with patch("builtins.print", side_effect=capture_print):
        verify_module.verify_outputs()

    assert any("OK" in line for line in outputs), f"Expected OK in output, got: {outputs}"


def test_verify_outputs_fail_zero_volume_mismatch(tmp_path, monkeypatch):
    """verify_outputs fails if zero_volume_bars_count mismatches."""
    monkeypatch.chdir(tmp_path)

    df = pd.DataFrame({
        "ts": pd.date_range("2023-01-01", periods=50, freq="h", tz="UTC"),
        "open": [100.0] * 50,
        "high": [101.0] * 50,
        "low": [99.0] * 50,
        "close": [100.5] * 50,
        "volume": [1000.0] * 50,
    })

    data_dir = tmp_path / "data" / "clean"
    data_dir.mkdir(parents=True, exist_ok=True)
    filename = symbol_to_filename("BTC/USDT", "1h")
    filepath = data_dir / filename
    save_parquet(df, str(filepath))

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "timeframe": "1h",
        "symbols": ["BTC/USDT"],
        "global": {},
        "per_symbol": [
            {
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "rows_total": 50,
                "first_ts": str(df["ts"].min()),
                "last_ts": str(df["ts"].max()),
                "expected_bars_count": 50,
                "missing_bars_count": 0,
                "missing_ratio": 0.0,
                "gaps_count": 0,
                "gap_ranges": [],
                "duplicates_count": 0,
                "zero_volume_bars_count": 1,
                "high_lt_low_count": 0,
                "negative_price_count": 0,
                "nan_count": 0,
                "sha256": "dummy",
            }
        ],
    }

    report_path = reports_dir / "data_quality.json"
    with open(report_path, "w") as f:
        json.dump(report, f)

    from buff.data import verify_outputs as verify_module
    outputs = []

    def capture_print(*args, **kwargs):
        outputs.append(" ".join(str(arg) for arg in args))

    with patch("builtins.print", side_effect=capture_print):
        verify_module.verify_outputs()

    assert any("ERROR" in line for line in outputs),         f"Expected error in output, got: {outputs}"


def test_verify_outputs_fail_gap_range_in_data(tmp_path, monkeypatch):
    """verify_outputs fails if gap_ranges include timestamps present in data."""
    monkeypatch.chdir(tmp_path)

    df = pd.DataFrame({
        "ts": pd.date_range("2023-01-01", periods=50, freq="h", tz="UTC"),
        "open": [100.0] * 50,
        "high": [101.0] * 50,
        "low": [99.0] * 50,
        "close": [100.5] * 50,
        "volume": [1000.0] * 50,
    })

    data_dir = tmp_path / "data" / "clean"
    data_dir.mkdir(parents=True, exist_ok=True)
    filename = symbol_to_filename("BTC/USDT", "1h")
    filepath = data_dir / filename
    save_parquet(df, str(filepath))

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "timeframe": "1h",
        "symbols": ["BTC/USDT"],
        "global": {},
        "per_symbol": [
            {
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "rows_total": 50,
                "first_ts": str(df["ts"].min()),
                "last_ts": str(df["ts"].max()),
                "expected_bars_count": 50,
                "missing_bars_count": 1,
                "missing_ratio": 0.02,
                "gaps_count": 1,
                "gap_ranges": [
                    {
                        "start": str(df["ts"].iloc[0]),
                        "end": str(df["ts"].iloc[0]),
                        "missing_bars": 1,
                    }
                ],
                "duplicates_count": 0,
                "zero_volume_bars_count": 0,
                "high_lt_low_count": 0,
                "negative_price_count": 0,
                "nan_count": 0,
                "sha256": "dummy",
            }
        ],
    }

    report_path = reports_dir / "data_quality.json"
    with open(report_path, "w") as f:
        json.dump(report, f)

    from buff.data import verify_outputs as verify_module
    outputs = []

    def capture_print(*args, **kwargs):
        outputs.append(" ".join(str(arg) for arg in args))

    with patch("builtins.print", side_effect=capture_print):
        verify_module.verify_outputs()

    assert any("ERROR" in line for line in outputs),         f"Expected error in output, got: {outputs}"


@pytest.mark.integration
def test_verify_outputs_report_missing(tmp_path, monkeypatch):
    """verify_outputs handles missing report gracefully."""
    monkeypatch.chdir(tmp_path)

    from buff.data import verify_outputs as verify_module
    outputs = []

    def capture_print(*args, **kwargs):
        outputs.append(" ".join(str(arg) for arg in args))

    with patch("builtins.print", side_effect=capture_print):
        verify_module.verify_outputs()

    assert any("not found" in line.lower() for line in outputs),         f"Expected 'not found' in output, got: {outputs}"
