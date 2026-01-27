"""Integration tests for verify_outputs with offline data."""

import json
from pathlib import Path
from io import StringIO
from unittest.mock import patch

import pandas as pd
import pytest

from buff.data.store import save_parquet, symbol_to_filename, load_parquet
from buff.data.validate import compute_quality


pytestmark = pytest.mark.integration


def create_test_parquet_and_report(tmp_path, symbol="BTC/USDT", rows=100):
    """Helper: create a parquet and report for testing."""
    # Create DataFrame
    df = pd.DataFrame({
        "ts": pd.date_range("2023-01-01", periods=rows, freq="h", tz="UTC"),
        "open": [100.0] * rows,
        "high": [101.0] * rows,
        "low": [99.0] * rows,
        "close": [100.5] * rows,
        "volume": [1000.0] * rows,
    })

    # Compute quality
    quality = compute_quality(df, "1h")

    # Save parquet
    data_dir = tmp_path / "data" / "clean"
    data_dir.mkdir(parents=True, exist_ok=True)
    filename = symbol_to_filename(symbol, "1h")
    filepath = data_dir / filename
    save_parquet(df, str(filepath))

    # Create report
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report = {
        symbol: {
            "rows": quality.rows,
            "start_ts": quality.start_ts,
            "end_ts": quality.end_ts,
            "duplicates": quality.duplicates,
            "missing_candles": quality.missing_candles,
            "missing_examples": quality.missing_examples,
            "zero_volume": quality.zero_volume,
            "zero_volume_examples": quality.zero_volume_examples,
            "file": str(filename),
        }
    }

    report_path = reports_dir / "data_quality.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    return df, quality, report


def test_verify_outputs_pass_correct_data(tmp_path, monkeypatch):
    """verify_outputs passes when data and report match."""
    monkeypatch.chdir(tmp_path)

    # Create valid parquet and report
    create_test_parquet_and_report(tmp_path, "BTC/USDT", rows=50)

    # Mock verify_outputs to capture output
    from buff.data import verify_outputs as verify_module
    outputs = []

    original_print = print
    def capture_print(*args, **kwargs):
        outputs.append(" ".join(str(arg) for arg in args))

    with patch("builtins.print", side_effect=capture_print):
        verify_module.verify_outputs()

    # Should pass
    assert any("OK" in line for line in outputs), f"Expected OK in output, got: {outputs}"


def test_verify_outputs_fail_zero_volume_mismatch(tmp_path, monkeypatch):
    """verify_outputs fails if zero_volume_examples don't have volume <= 0."""
    monkeypatch.chdir(tmp_path)

    # Create parquet
    df = pd.DataFrame({
        "ts": pd.date_range("2023-01-01", periods=50, freq="h", tz="UTC"),
        "open": [100.0] * 50,
        "high": [101.0] * 50,
        "low": [99.0] * 50,
        "close": [100.5] * 50,
        "volume": [1000.0] * 50,  # All positive volume
    })

    data_dir = tmp_path / "data" / "clean"
    data_dir.mkdir(parents=True, exist_ok=True)
    filename = symbol_to_filename("BTC/USDT", "1h")
    filepath = data_dir / filename
    save_parquet(df, str(filepath))

    # Create report with WRONG zero_volume_examples
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "BTC/USDT": {
            "rows": 50,
            "start_ts": str(df["ts"].min()),
            "end_ts": str(df["ts"].max()),
            "duplicates": 0,
            "missing_candles": 0,
            "missing_examples": [],
            "zero_volume": 1,
            "zero_volume_examples": ["2023-01-01 12:00:00+00:00"],  # This has vol=1000, not <=0
            "file": str(filename),
        }
    }

    report_path = reports_dir / "data_quality.json"
    with open(report_path, "w") as f:
        json.dump(report, f)

    # verify_outputs should fail
    from buff.data import verify_outputs as verify_module
    outputs = []

    def capture_print(*args, **kwargs):
        outputs.append(" ".join(str(arg) for arg in args))

    with patch("builtins.print", side_effect=capture_print):
        verify_module.verify_outputs()

    # Should have error
    assert any("✗" in line or "failed" in line.lower() for line in outputs), \
        f"Expected error in output, got: {outputs}"


def test_verify_outputs_fail_missing_example_in_data(tmp_path, monkeypatch):
    """verify_outputs fails if missing_examples are actually in data."""
    monkeypatch.chdir(tmp_path)

    # Create parquet with data
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

    # Create report with WRONG missing_examples (ts that exists in data)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "BTC/USDT": {
            "rows": 50,
            "start_ts": str(df["ts"].min()),
            "end_ts": str(df["ts"].max()),
            "duplicates": 0,
            "missing_candles": 1,
            "missing_examples": [str(df["ts"].iloc[0])],  # This timestamp EXISTS, shouldn't be in missing
            "zero_volume": 0,
            "zero_volume_examples": [],
            "file": str(filename),
        }
    }

    report_path = reports_dir / "data_quality.json"
    with open(report_path, "w") as f:
        json.dump(report, f)

    # verify_outputs should fail
    from buff.data import verify_outputs as verify_module
    outputs = []

    def capture_print(*args, **kwargs):
        outputs.append(" ".join(str(arg) for arg in args))

    with patch("builtins.print", side_effect=capture_print):
        verify_module.verify_outputs()

    # Should have error
    assert any("✗" in line or "found in data" in line for line in outputs), \
        f"Expected error in output, got: {outputs}"


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

    # Should print error about missing report
    assert any("not found" in line.lower() for line in outputs), \
        f"Expected 'not found' in output, got: {outputs}"
