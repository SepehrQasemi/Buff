from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data.store import write_parquet_1m

MS = 60_000


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_df(start_ms: int, symbol: str = "BTCUSDT") -> pd.DataFrame:
    timestamps = [start_ms + 2 * MS, start_ms, start_ms + MS]
    data = {
        "symbol": [symbol, symbol, symbol],
        "timestamp": timestamps,
        "open": [100.0, 101.0, 102.0],
        "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0],
        "close": [100.5, 101.5, 102.5],
        "volume": [1.0, 2.0, 3.0],
    }
    return pd.DataFrame(data)


def test_parquet_reproducible_and_sorted(tmp_path: Path) -> None:
    df = _make_df(1_700_000_000_000)
    path_a = write_parquet_1m(df, tmp_path / "out_a", "BTCUSDT")
    path_b = write_parquet_1m(df, tmp_path / "out_b", "BTCUSDT")

    assert _sha256(path_a) == _sha256(path_b)

    schema = pq.read_schema(path_a)
    expected = pa.schema(
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
    assert schema == expected

    table = pq.read_table(path_a)
    df_read = table.to_pandas()
    assert list(df_read.columns) == [
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    assert df_read["timestamp"].is_monotonic_increasing
