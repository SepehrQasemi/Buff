from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

import pyarrow as pa
import pyarrow.parquet as pq


PARQUET_COMPRESSION = "zstd"
PARQUET_COMPRESSION_LEVEL = 3
PARQUET_ROW_GROUP_SIZE = 50_000
PARQUET_DATA_PAGE_SIZE = 1_048_576
PARQUET_WRITE_STATISTICS = False

TRADE_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("ts_utc", pa.string()),
        ("order_id", pa.string()),
        ("symbol", pa.string()),
        ("side", pa.string()),
        ("qty", pa.float64()),
        ("status", pa.string()),
        ("reason", pa.string()),
        ("execution_status", pa.string()),
    ]
)


def _coerce_str(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _coerce_float(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_trade(trade: Mapping[str, object]) -> dict[str, object]:
    return {
        "run_id": _coerce_str(trade.get("run_id")),
        "ts_utc": _coerce_str(trade.get("ts_utc")),
        "order_id": _coerce_str(trade.get("order_id")),
        "symbol": _coerce_str(trade.get("symbol")),
        "side": _coerce_str(trade.get("side")),
        "qty": _coerce_float(trade.get("qty")),
        "status": _coerce_str(trade.get("status")),
        "reason": _coerce_str(trade.get("reason")),
        "execution_status": _coerce_str(trade.get("execution_status")),
    }


def write_trades_parquet(path: Path, trades: Iterable[Mapping[str, object]]) -> Path:
    normalized = [_normalize_trade(trade) for trade in trades]
    normalized.sort(key=lambda item: (item["ts_utc"], item["order_id"], item["symbol"]))
    table = pa.Table.from_pylist(normalized, schema=TRADE_SCHEMA)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        path,
        compression=PARQUET_COMPRESSION,
        compression_level=PARQUET_COMPRESSION_LEVEL,
        row_group_size=PARQUET_ROW_GROUP_SIZE,
        data_page_size=PARQUET_DATA_PAGE_SIZE,
        write_statistics=PARQUET_WRITE_STATISTICS,
    )
    return path
