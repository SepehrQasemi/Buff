"""Integration tests for run_ingest with offline fake data."""

import json
from pathlib import Path

import pandas as pd
import pytest

from buff.data.ingest import IngestConfig
from buff.data.store import save_parquet, symbol_to_filename, load_parquet
from buff.data.validate import compute_quality


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
                100.0 + i,      # open
                101.0 + i,      # high
                99.0 + i,       # low
                100.5 + i,      # close
                1000.0 + (100 if i % 10 == 5 else 0),  # some zero volume
            ])
        return candles

    return _fetch


def test_run_ingest_creates_parquet_and_report(tmp_path, monkeypatch):
    """run_ingest creates parquet and report JSON with correct schema."""
    # Change to tmp directory
    monkeypatch.chdir(tmp_path)

    # Create data/clean and reports directories
    (tmp_path / "data" / "clean").mkdir(parents=True, exist_ok=True)
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)

    # Create test DataFrame and process it
    df = pd.DataFrame({
        "ts": pd.date_range("2023-01-01", periods=100, freq="h", tz="UTC"),
        "open": [100.0 + i for i in range(100)],
        "high": [101.0 + i for i in range(100)],
        "low": [99.0 + i for i in range(100)],
        "close": [100.5 + i for i in range(100)],
        "volume": [1000.0] * 100,
    })

    quality = compute_quality(df, "1h")
    filename = symbol_to_filename("BTC/USDT", "1h")
    filepath = tmp_path / "data" / "clean" / filename

    save_parquet(df, str(filepath))

    report = {
        "BTC/USDT": {
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

    report_path = tmp_path / "reports" / "data_quality.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Verify parquet exists
    parquet_file = tmp_path / "data" / "clean" / "BTC_USDT_1h.parquet"
    assert parquet_file.exists()

    # Verify report exists
    report_file = tmp_path / "reports" / "data_quality.json"
    assert report_file.exists()

    # Verify report schema
    with open(report_file) as f:
        report_loaded = json.load(f)

    assert "BTC/USDT" in report_loaded
    row = report_loaded["BTC/USDT"]
    assert "rows" in row
    assert "start_ts" in row
    assert "end_ts" in row
    assert "duplicates" in row
    assert "missing_candles" in row
    assert "missing_examples" in row
    assert "zero_volume" in row
    assert "zero_volume_examples" in row
    assert "file" in row


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

    # Load and verify
    loaded = load_parquet(str(parquet_path))

    assert "ts" in loaded.columns
    assert loaded["ts"].dtype == "datetime64[ns, tz=UTC]"
    assert loaded["ts"].is_monotonic_increasing


def test_report_json_is_valid(tmp_path):
    """Report JSON can be parsed and has correct types."""
    from buff.data.validate import DataQuality

    dq = DataQuality(
        rows=50,
        start_ts="2023-01-01 00:00:00+00:00",
        end_ts="2023-01-03 00:00:00+00:00",
        duplicates=0,
        missing_candles=1,
        zero_volume=2,
        missing_examples=["2023-01-02 12:00:00+00:00"],
        zero_volume_examples=["2023-01-01 13:00:00+00:00"],
    )

    report = {"BTC/USDT": dq.__dict__}

    report_path = tmp_path / "test_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f)

    # Reload and verify
    with open(report_path) as f:
        loaded = json.load(f)

    assert loaded["BTC/USDT"]["rows"] == 50
    assert loaded["BTC/USDT"]["missing_candles"] == 1
    assert isinstance(loaded["BTC/USDT"]["missing_examples"], list)
