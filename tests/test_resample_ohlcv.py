from __future__ import annotations

import pandas as pd

from data.resample_ohlcv import resample_ohlcv


def _frame(start: str, periods: int) -> pd.DataFrame:
    ts = pd.date_range(start, periods=periods, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "ts": ts,
            "open": list(range(periods)),
            "high": [v + 1 for v in range(periods)],
            "low": [v - 1 for v in range(periods)],
            "close": [v + 0.5 for v in range(periods)],
            "volume": [1.0] * periods,
        }
    )


def test_basic_aggregation_correctness() -> None:
    df = _frame("2023-01-01T00:00:00Z", 5)
    out = resample_ohlcv(df, 300)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["ts"].isoformat().startswith("2023-01-01T00:00:00")
    assert row["open"] == 0
    assert row["high"] == 5
    assert row["low"] == -1
    assert row["close"] == 4.5
    assert row["volume"] == 5.0


def test_utc_boundary_alignment() -> None:
    df = _frame("2023-01-01T00:02:00Z", 5)
    out = resample_ohlcv(df, 300)
    assert out.empty


def test_no_lookahead_truncation_changes_output() -> None:
    df_full = _frame("2023-01-01T00:00:00Z", 10)
    out_full = resample_ohlcv(df_full, 300)
    df_trunc = df_full.iloc[:-1].copy()
    out_trunc = resample_ohlcv(df_trunc, 300)
    assert len(out_full) == 2
    assert len(out_trunc) == 1


def test_determinism_byte_for_byte() -> None:
    df = _frame("2023-01-01T00:00:00Z", 10)
    out_a = resample_ohlcv(df, 300)
    out_b = resample_ohlcv(df, 300)
    bytes_a = out_a.to_csv(index=False).encode("utf-8")
    bytes_b = out_b.to_csv(index=False).encode("utf-8")
    assert bytes_a == bytes_b


def test_behavior_on_out_of_order_or_duplicate_input() -> None:
    df = _frame("2023-01-01T00:00:00Z", 3)
    df_out_of_order = df.iloc[[1, 0, 2]].copy()
    try:
        resample_ohlcv(df_out_of_order, 300)
        assert False, "expected timestamps_not_sorted"
    except ValueError as exc:
        assert str(exc) == "timestamps_not_sorted"

    df_dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    try:
        resample_ohlcv(df_dup, 300)
        assert False, "expected duplicate_timestamps"
    except ValueError as exc:
        assert str(exc) == "duplicate_timestamps"
