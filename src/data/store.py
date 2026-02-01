"""Deterministic parquet storage for 1m OHLCV."""

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


def write_parquet_1m(df: pd.DataFrame, out_dir: Path, symbol: str) -> Path:
    """Write 1m OHLCV parquet with deterministic schema and ordering."""
    out_path = out_dir / "ohlcv_1m" / f"{symbol}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ordered = df[CANONICAL_COLUMNS].copy()
    ordered["symbol"] = ordered["symbol"].astype("string")
    ordered["timestamp"] = ordered["timestamp"].astype("int64")
    for col in ["open", "high", "low", "close", "volume"]:
        ordered[col] = ordered[col].astype("float64")

    ordered = ordered.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    table = pa.Table.from_pandas(ordered, schema=PARQUET_SCHEMA, preserve_index=False)
    table = table.replace_schema_metadata(None)
    pq.write_table(table, out_path, compression="zstd", use_dictionary=False)
    return out_path
