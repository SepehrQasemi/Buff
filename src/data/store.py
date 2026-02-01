"""Deterministic Parquet storage for OHLCV data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PARQUET_SCHEMA = pa.schema(
    [
        ("symbol", pa.string()),
        ("timestamp", pa.int64()),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.float64()),
    ]
)

CANONICAL_COLUMNS = ["symbol", "timestamp", "open", "high", "low", "close", "volume"]
ROW_GROUP_SIZE = 100_000
DATA_PAGE_SIZE = 1_048_576
WRITE_STATISTICS = False
COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3


def parquet_path(out_dir: Path, symbol: str, timeframe: str) -> Path:
    """Return deterministic parquet path partitioned by symbol/timeframe."""
    return out_dir / symbol / timeframe / "data.parquet"


def _prepare_frame(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    required = set(CANONICAL_COLUMNS)
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    unique_symbols = set(df["symbol"].dropna().astype(str).unique())
    if unique_symbols and unique_symbols != {symbol}:
        raise ValueError(f"Data contains multiple symbols: {sorted(unique_symbols)}")

    ordered = df[CANONICAL_COLUMNS].copy()
    ordered["symbol"] = ordered["symbol"].astype("string")
    ordered["timestamp"] = ordered["timestamp"].astype("int64")
    for col in ["open", "high", "low", "close", "volume"]:
        ordered[col] = ordered[col].astype("float64")

    ordered = ordered.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return ordered


def write_parquet(df: pd.DataFrame, out_dir: Path, symbol: str, timeframe: str) -> Path:
    """Write OHLCV parquet with deterministic schema and ordering."""
    out_path = parquet_path(out_dir, symbol, timeframe)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ordered = _prepare_frame(df, symbol)

    table = pa.Table.from_pandas(ordered, schema=PARQUET_SCHEMA, preserve_index=False)
    table = table.replace_schema_metadata(None)
    pq.write_table(
        table,
        out_path,
        compression=COMPRESSION,
        compression_level=COMPRESSION_LEVEL,
        use_dictionary=False,
        row_group_size=ROW_GROUP_SIZE,
        data_page_size=DATA_PAGE_SIZE,
        write_statistics=WRITE_STATISTICS,
    )
    return out_path


def write_parquet_1m(df: pd.DataFrame, out_dir: Path, symbol: str) -> Path:
    """Write 1m OHLCV parquet with deterministic schema and ordering."""
    return write_parquet(df, out_dir, symbol, "1m")
