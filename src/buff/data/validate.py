"""Data quality validation and reporting."""

from dataclasses import dataclass
from pathlib import Path
import argparse

import pandas as pd

from buff.data.store import ohlcv_parquet_path


@dataclass
class DataQuality:
    """Data quality metrics with examples for debugging."""

    rows: int
    start_ts: str
    end_ts: str
    duplicates: int
    missing_candles: int
    zero_volume: int
    missing_examples: list[str]  # Up to 5 example timestamps of missing candles
    zero_volume_examples: list[str]  # Up to 5 example timestamps of zero-volume candles


def expected_step_seconds(timeframe: str) -> int:
    """Convert timeframe string to expected step in seconds.

    Args:
        timeframe: Timeframe string (e.g., "1h", "15m", "1d").

    Returns:
        Expected step in seconds.
    """

    if timeframe.endswith("m"):
        minutes = int(timeframe[:-1])
        return minutes * 60
    elif timeframe.endswith("h"):
        hours = int(timeframe[:-1])
        return hours * 3600
    elif timeframe.endswith("d"):
        days = int(timeframe[:-1])
        return days * 86400
    elif timeframe.endswith("w"):
        weeks = int(timeframe[:-1])
        return weeks * 604800
    else:
        raise ValueError(f"Unknown timeframe: {timeframe}")


def calendar_freq(timeframe: str) -> str | None:
    """Return pandas frequency string for calendar-based timeframes."""
    mapping = {
        "1M": "MS",
        "3M": "QS-JAN",
        "6M": "2QS-JAN",
        "1Y": "YS",
    }
    return mapping.get(timeframe)


def compute_quality(df: pd.DataFrame, timeframe: str) -> DataQuality:
    """Compute data quality metrics for a OHLCV DataFrame.

    Args:
        df: DataFrame with columns ts, open, high, low, close, volume.
               ts must be datetime64[ns, UTC].
        timeframe: Timeframe string (e.g., "1h").

    Returns:
        DataQuality instance with counts and examples.
    """
    rows = len(df)

    if rows == 0:
        return DataQuality(
            rows=0,
            start_ts="",
            end_ts="",
            duplicates=0,
            missing_candles=0,
            zero_volume=0,
            missing_examples=[],
            zero_volume_examples=[],
        )

    start_ts = str(df["ts"].min())
    end_ts = str(df["ts"].max())

    # Count duplicate timestamps (convert numpy.int64 to Python int)
    duplicates = int(df["ts"].duplicated().sum())

    # Count and find zero volume candles
    zero_vol_mask = df["volume"] <= 0
    zero_volume = int(zero_vol_mask.sum())
    zero_volume_examples = [str(ts) for ts in df.loc[zero_vol_mask, "ts"].head(5)]

    missing_candles = 0
    missing_examples_list = []
    freq = calendar_freq(timeframe)
    if freq:
        expected = pd.date_range(df["ts"].iloc[0], df["ts"].iloc[-1], freq=freq, tz="UTC")
        actual = set(df["ts"])
        missing = [ts for ts in expected if ts not in actual]
        missing_candles = len(missing)
        missing_examples_list = [str(ts) for ts in missing[:5]]
    else:
        expected_step = expected_step_seconds(timeframe)
        ts_diff = df["ts"].diff().dt.total_seconds()

        for i, diff in enumerate(ts_diff.iloc[1:], start=1):
            if pd.notna(diff) and diff > expected_step:
                num_missing = int((diff / expected_step) - 1)
                missing_candles += num_missing

                prev_ts = df["ts"].iloc[i - 1]

                for j in range(1, num_missing + 1):
                    if len(missing_examples_list) < 5:
                        missing_ts = prev_ts + pd.Timedelta(seconds=j * expected_step)
                        missing_examples_list.append(str(missing_ts))

    return DataQuality(
        rows=rows,
        start_ts=start_ts,
        end_ts=end_ts,
        duplicates=duplicates,
        missing_candles=missing_candles,
        zero_volume=zero_volume,
        missing_examples=missing_examples_list,
        zero_volume_examples=zero_volume_examples,
    )


def _discover_timeframes(data_dir: Path) -> list[str]:
    return sorted(
        path.name.split("=", 1)[1]
        for path in data_dir.glob("timeframe=*")
        if path.is_dir() and "=" in path.name
    )


def _discover_symbols(data_dir: Path, timeframe: str) -> list[str]:
    symbol_dirs = sorted((data_dir / f"timeframe={timeframe}").glob("symbol=*"))
    symbols = []
    for path in symbol_dirs:
        part = path.name.split("=", 1)[1]
        symbols.append(part)
    return symbols


def _normalize_symbol(symbol: str) -> str:
    if "/" in symbol:
        return symbol
    if symbol.endswith("USDT") and len(symbol) > 4:
        return f"{symbol[:-4]}/USDT"
    return symbol


def _validate_ohlcv(df: pd.DataFrame, symbol: str) -> None:
    required = {"ts", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{symbol} missing required columns: {missing}")

    price_cols = ["open", "high", "low", "close"]
    nan_count = int(df[price_cols + ["volume"]].isna().any(axis=1).sum())
    negative_price_count = int((df[price_cols] < 0).any(axis=1).sum())
    if nan_count > 0 or negative_price_count > 0:
        raise ValueError(
            f"{symbol} invalid OHLCV: nan_count={nan_count}, negative_price_count={negative_price_count}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate OHLCV parquet files.")
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="Comma-separated symbols (e.g., BTCUSDT,ETHUSDT). If omitted, auto-detect.",
    )
    parser.add_argument("--timeframes", type=str, default="", help="Comma-separated timeframes")
    parser.add_argument("--timeframe", type=str, default="", help="Single timeframe (deprecated)")
    parser.add_argument(
        "--data_dir",
        type=str,
        required=True,
        help="Directory containing parquet files.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if args.timeframes:
        timeframes = [tf.strip() for tf in args.timeframes.split(",") if tf.strip()]
    elif args.timeframe:
        timeframes = [args.timeframe]
    else:
        timeframes = _discover_timeframes(data_dir)

    if args.symbols:
        symbols = [_normalize_symbol(sym.strip()) for sym in args.symbols.split(",") if sym.strip()]
    else:
        symbols = []

    if not timeframes:
        raise ValueError("No timeframes found for validation.")

    from buff.data.store import load_parquet

    for timeframe in sorted(set(timeframes)):
        symbol_list = symbols or _discover_symbols(data_dir, timeframe)
        if not symbol_list:
            raise ValueError(f"No symbols found for timeframe {timeframe}")
        for symbol in sorted(set(symbol_list)):
            symbol_norm = _normalize_symbol(symbol)
            path = ohlcv_parquet_path(data_dir, symbol_norm, timeframe)
            df = load_parquet(str(path))
            _validate_ohlcv(df, symbol_norm)
            quality = compute_quality(df, timeframe)
            print(
                f"{symbol_norm} {timeframe} rows={quality.rows} "
                f"duplicates={quality.duplicates} missing={quality.missing_candles} "
                f"zero_volume={quality.zero_volume}"
            )


if __name__ == "__main__":
    main()
