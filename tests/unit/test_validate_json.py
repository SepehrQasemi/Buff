"""Unit tests for JSON serialization of validation output."""

import json
from pathlib import Path

import pandas as pd
import pytest

from buff.data.report import build_report
from buff.data.store import ohlcv_parquet_path, save_parquet
from buff.data.validate import DataQuality, compute_quality


pytestmark = pytest.mark.unit


class TestDataQualityJSONSerializable:
    """Test that DataQuality output is JSON-serializable (no numpy types)."""

    def test_dataclass_to_json(self) -> None:
        dq = DataQuality(
            rows=100,
            start_ts="2023-01-01 00:00:00+00:00",
            end_ts="2023-01-05 00:00:00+00:00",
            duplicates=0,
            missing_candles=2,
            zero_volume=1,
            missing_examples=["2023-01-02 12:00:00+00:00", "2023-01-03 13:00:00+00:00"],
            zero_volume_examples=["2023-01-04 14:00:00+00:00"],
        )

        json_str = json.dumps(dq.__dict__)
        assert json_str is not None
        assert '"rows": 100' in json_str
        assert '"duplicates": 0' in json_str

    def test_compute_quality_output_no_numpy_types(self) -> None:
        df = pd.DataFrame({
            "ts": pd.date_range("2023-01-01", periods=100, freq="1min", tz="UTC"),
            "open": [100.0] * 100,
            "high": [101.0] * 100,
            "low": [99.0] * 100,
            "close": [100.5] * 100,
            "volume": [1000.0] * 100,
        })

        quality = compute_quality(df, "1m")

        assert isinstance(quality.rows, int)
        assert isinstance(quality.duplicates, int)
        assert isinstance(quality.missing_candles, int)
        assert isinstance(quality.zero_volume, int)

        json_str = json.dumps(quality.__dict__)
        assert json_str is not None

    def test_full_report_dict_serializable(self, tmp_path: Path) -> None:
        df = pd.DataFrame({
            "ts": pd.date_range("2023-01-01", periods=50, freq="1min", tz="UTC"),
            "open": [100.0] * 50,
            "high": [101.0] * 50,
            "low": [99.0] * 50,
            "close": [100.5] * 50,
            "volume": [1000.0] * 50,
        })

        data_dir = tmp_path / "data" / "ohlcv"
        save_parquet(df, str(ohlcv_parquet_path(data_dir, "BTC/USDT", "1m")))

        report = build_report(data_dir, ["BTC/USDT"], ["1m"], strict=False)

        json_str = json.dumps(report)
        assert json_str is not None

        loaded = json.loads(json_str)
        assert loaded["per_symbol"][0]["rows_total"] == 50
        assert loaded["per_symbol"][0]["missing_bars_count"] == 0

    def test_empty_examples_list_serializable(self) -> None:
        dq = DataQuality(
            rows=10,
            start_ts="2023-01-01 00:00:00+00:00",
            end_ts="2023-01-01 10:00:00+00:00",
            duplicates=0,
            missing_candles=0,
            zero_volume=0,
            missing_examples=[],
            zero_volume_examples=[],
        )

        json_str = json.dumps(dq.__dict__)
        loaded = json.loads(json_str)

        assert loaded["missing_examples"] == []
        assert loaded["zero_volume_examples"] == []
