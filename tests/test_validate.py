"""Unit tests for data validation logic."""

import pandas as pd
import pytest

from src.data.validate import compute_quality, expected_step_seconds


class TestExpectedStepSeconds:
    """Tests for expected_step_seconds."""

    def test_1h_timeframe(self) -> None:
        """1h should return 3600 seconds."""
        assert expected_step_seconds("1h") == 3600

    def test_4h_timeframe(self) -> None:
        """4h should return 14400 seconds."""
        assert expected_step_seconds("4h") == 14400

    def test_1d_timeframe(self) -> None:
        """1d should return 86400 seconds."""
        assert expected_step_seconds("1d") == 86400

    def test_15m_timeframe(self) -> None:
        """15m should return 900 seconds."""
        assert expected_step_seconds("15m") == 900

    def test_unknown_timeframe(self) -> None:
        """Unknown timeframe should raise ValueError."""
        with pytest.raises(ValueError):
            expected_step_seconds("xyz")


class TestComputeQuality:
    """Tests for compute_quality."""

    def test_empty_dataframe(self) -> None:
        """Empty DataFrame should return 0 values."""
        df = pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        quality = compute_quality(df, "1h")

        assert quality.rows == 0
        assert quality.start_ts == ""
        assert quality.end_ts == ""
        assert quality.duplicates == 0
        assert quality.missing_candles == 0
        assert quality.zero_volume == 0

    def test_no_duplicates_no_gaps_no_zero_volume(self) -> None:
        """Clean data should report 0 issues."""
        dates = pd.date_range("2022-01-01", periods=5, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {
                "ts": dates,
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "high": [101.0, 102.0, 103.0, 104.0, 105.0],
                "low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "close": [100.5, 101.5, 102.5, 103.5, 104.5],
                "volume": [1000.0, 1100.0, 1200.0, 1300.0, 1400.0],
            }
        )

        quality = compute_quality(df, "1h")

        assert quality.rows == 5
        assert quality.duplicates == 0
        assert quality.missing_candles == 0
        assert quality.zero_volume == 0

    def test_duplicate_timestamps(self) -> None:
        """Duplicate timestamps should be counted."""
        dates = pd.date_range("2022-01-01", periods=5, freq="1h", tz="UTC")
        dates_with_dup = pd.DatetimeIndex(
            list(dates) + [dates[1]]
        )  # Duplicate second timestamp
        df = pd.DataFrame(
            {
                "ts": dates_with_dup,
                "open": [100.0] * 6,
                "high": [101.0] * 6,
                "low": [99.0] * 6,
                "close": [100.5] * 6,
                "volume": [1000.0] * 6,
            }
        )

        quality = compute_quality(df, "1h")

        assert quality.duplicates == 1

    def test_zero_volume_candles(self) -> None:
        """Zero volume candles should be counted."""
        dates = pd.date_range("2022-01-01", periods=5, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {
                "ts": dates,
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "high": [101.0, 102.0, 103.0, 104.0, 105.0],
                "low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "close": [100.5, 101.5, 102.5, 103.5, 104.5],
                "volume": [1000.0, 0.0, 1200.0, -50.0, 1400.0],  # 2 problematic
            }
        )

        quality = compute_quality(df, "1h")

        assert quality.zero_volume == 2

    def test_missing_candles_with_gap(self) -> None:
        """Missing candles should be detected from timestamp gaps."""
        # Create 3 candles: at 00:00, 01:00, and 03:00 (missing 02:00)
        dates = pd.DatetimeIndex(
            [
                pd.Timestamp("2022-01-01 00:00", tz="UTC"),
                pd.Timestamp("2022-01-01 01:00", tz="UTC"),
                pd.Timestamp("2022-01-01 03:00", tz="UTC"),
            ]
        )
        df = pd.DataFrame(
            {
                "ts": dates,
                "open": [100.0, 101.0, 103.0],
                "high": [101.0, 102.0, 104.0],
                "low": [99.0, 100.0, 102.0],
                "close": [100.5, 101.5, 103.5],
                "volume": [1000.0, 1100.0, 1300.0],
            }
        )

        quality = compute_quality(df, "1h")

        # Gap between 01:00 and 03:00 is 2 hours (7200 seconds)
        # Expected is 3600, so missing = (7200 / 3600) - 1 = 2 - 1 = 1
        assert quality.missing_candles == 1

    def test_missing_candles_large_gap(self) -> None:
        """Large gaps should count multiple missing candles."""
        # Create 2 candles: at 00:00 and 06:00 (missing 5 candles)
        dates = pd.DatetimeIndex(
            [
                pd.Timestamp("2022-01-01 00:00", tz="UTC"),
                pd.Timestamp("2022-01-01 06:00", tz="UTC"),
            ]
        )
        df = pd.DataFrame(
            {
                "ts": dates,
                "open": [100.0, 106.0],
                "high": [101.0, 107.0],
                "low": [99.0, 105.0],
                "close": [100.5, 106.5],
                "volume": [1000.0, 6000.0],
            }
        )

        quality = compute_quality(df, "1h")

        # Gap is 6 hours (21600 seconds)
        # missing = (21600 / 3600) - 1 = 6 - 1 = 5
        assert quality.missing_candles == 5

    def test_start_and_end_timestamps(self) -> None:
        """start_ts and end_ts should match first and last."""
        dates = pd.date_range("2022-01-15", periods=3, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {
                "ts": dates,
                "open": [100.0, 101.0, 102.0],
                "high": [101.0, 102.0, 103.0],
                "low": [99.0, 100.0, 101.0],
                "close": [100.5, 101.5, 102.5],
                "volume": [1000.0, 1100.0, 1200.0],
            }
        )

        quality = compute_quality(df, "1h")

        assert "2022-01-15" in quality.start_ts
        assert "2022-01-15 02:00" in quality.end_ts

    def test_combined_issues(self) -> None:
        """Multiple issues should all be counted."""
        # Create candles with duplicates, gaps, and zero volume
        dates = pd.DatetimeIndex(
            [
                pd.Timestamp("2022-01-01 00:00", tz="UTC"),
                pd.Timestamp("2022-01-01 00:00", tz="UTC"),  # Duplicate
                pd.Timestamp("2022-01-01 01:00", tz="UTC"),
                pd.Timestamp("2022-01-01 03:00", tz="UTC"),  # Gap: missing 02:00
            ]
        )
        df = pd.DataFrame(
            {
                "ts": dates,
                "open": [100.0, 100.0, 101.0, 103.0],
                "high": [101.0, 101.0, 102.0, 104.0],
                "low": [99.0, 99.0, 100.0, 102.0],
                "close": [100.5, 100.5, 101.5, 103.5],
                "volume": [1000.0, 1000.0, 0.0, 1300.0],  # One zero volume
            }
        )

        quality = compute_quality(df, "1h")

        assert quality.duplicates == 1
        assert quality.missing_candles == 1
        assert quality.zero_volume == 1
    def test_missing_examples_extraction(self) -> None:
        """Missing candles examples should be correctly identified."""
        # Create 3 candles: at 00:00, 01:00, and 03:00 (missing 02:00)
        dates = pd.DatetimeIndex(
            [
                pd.Timestamp("2023-03-24 00:00", tz="UTC"),
                pd.Timestamp("2023-03-24 01:00", tz="UTC"),
                pd.Timestamp("2023-03-24 03:00", tz="UTC"),
            ]
        )
        df = pd.DataFrame(
            {
                "ts": dates,
                "open": [100.0, 101.0, 103.0],
                "high": [101.0, 102.0, 104.0],
                "low": [99.0, 100.0, 102.0],
                "close": [100.5, 101.5, 103.5],
                "volume": [1000.0, 1100.0, 1300.0],
            }
        )

        quality = compute_quality(df, "1h")

        # Should detect 1 missing candle
        assert quality.missing_candles == 1
        # Should have one example
        assert len(quality.missing_examples) == 1
        # Example should be the missing timestamp (02:00)
        assert "2023-03-24 02:00" in quality.missing_examples[0]

    def test_zero_volume_examples_extraction(self) -> None:
        """Zero volume examples should be correctly identified."""
        dates = pd.date_range("2023-03-24", periods=5, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {
                "ts": dates,
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "high": [101.0, 102.0, 103.0, 104.0, 105.0],
                "low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "close": [100.5, 101.5, 102.5, 103.5, 104.5],
                "volume": [1000.0, 0.0, 1200.0, 0.0, 1400.0],  # 2 zero volumes
            }
        )

        quality = compute_quality(df, "1h")

        # Should detect 2 zero volume candles
        assert quality.zero_volume == 2
        # Should have 2 examples
        assert len(quality.zero_volume_examples) == 2
        # First example should be 01:00
        assert "2023-03-24 01:00" in quality.zero_volume_examples[0]
        # Second example should be 03:00
        assert "2023-03-24 03:00" in quality.zero_volume_examples[1]