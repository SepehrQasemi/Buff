"""Parquet storage and retrieval."""

from pathlib import Path

import pandas as pd


def symbol_to_filename(symbol: str, timeframe: str) -> str:
    """Convert symbol and timeframe to parquet filename.

    Args:
        symbol: Trading pair symbol (e.g., "BTC/USDT").
        timeframe: Timeframe (e.g., "1h").

    Returns:
        Filename string (e.g., "BTC_USDT_1h.parquet").
    """
    clean_symbol = symbol.replace("/", "_")
    return f"{clean_symbol}_{timeframe}.parquet"


def symbol_to_partition(symbol: str) -> str:
    """Convert symbol to partition-friendly format (e.g., BTCUSDT)."""
    return symbol.replace("/", "")


def ohlcv_parquet_path(base_dir: Path, symbol: str, timeframe: str) -> Path:
    """Return deterministic parquet path for a symbol/timeframe."""
    symbol_part = symbol_to_partition(symbol)
    return base_dir / f"timeframe={timeframe}" / f"symbol={symbol_part}" / "ohlcv.parquet"


def save_parquet(df: pd.DataFrame, path: str) -> None:
    """Save DataFrame to parquet file.

    Args:
        df: DataFrame with ts column as datetime64[ns, UTC].
        path: Full path to output parquet file.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, engine="pyarrow", index=False)


def load_parquet(path: str) -> pd.DataFrame:
    """Load DataFrame from parquet file.

    Args:
        path: Full path to parquet file.

    Returns:
        DataFrame with ts column as datetime64[ns, UTC].
    """
    df = pd.read_parquet(path, engine="pyarrow")
    if "ts" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["ts"]):
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df
