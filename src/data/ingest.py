"""Compatibility shim for explicit offline ingest entrypoints.

Network-capable ingestion helpers live in `data.offline_binance_ingest`.
Core risk/execution runtime modules must not import this shim.
"""

from __future__ import annotations

from . import offline_binance_ingest as _offline
from .offline_binance_ingest import (  # noqa: F401
    DEFAULT_MAX_RETRIES,
    DEFAULT_RATE_LIMIT_SLEEP,
    DEFAULT_TIMEOUT_SECONDS,
    INTERVAL_1M,
    KLINES_ENDPOINT,
    KLINES_LIMIT,
    MS_PER_MINUTE,
    OUTPUT_COLUMNS,
    download_ohlcv_1m,
    fetch_klines_1m,
)


def __getattr__(name: str) -> object:
    return getattr(_offline, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_offline)))
