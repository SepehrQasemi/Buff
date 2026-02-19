"""Explicit offline-ingest module for deterministic Binance OHLCV downloads.

This module is intentionally separate from core runtime (risk/execution) paths.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"
KLINES_ENDPOINT = "/fapi/v1/klines"
INTERVAL_1M = "1m"
KLINES_LIMIT = 1500
MS_PER_MINUTE = 60_000
DEFAULT_RATE_LIMIT_SLEEP = 0.1
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 5

OUTPUT_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "symbol"]


def _normalize_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if "/" in cleaned:
        cleaned = cleaned.replace("/", "")
    return cleaned


def _floor_ms_to_minute(ms: int) -> int:
    return (ms // MS_PER_MINUTE) * MS_PER_MINUTE


def _ceil_ms_to_minute(ms: int) -> int:
    if ms % MS_PER_MINUTE == 0:
        return ms
    return ((ms // MS_PER_MINUTE) + 1) * MS_PER_MINUTE


def _parse_time_to_utc_ms(value: str | datetime | int, *, rounding: str) -> int:
    """Parse ISO-8601 string, datetime, or ms to UTC ms and align to minute.

    Naive datetimes or date-only strings are assumed to be UTC.
    Rounding must be 'floor' (start) or 'ceil' (exclusive end).
    """
    if isinstance(value, int):
        ms = value
    else:
        if isinstance(value, datetime):
            dt = value
        else:
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        ms = int(dt.timestamp() * 1000)

    if rounding == "floor":
        return _floor_ms_to_minute(ms)
    if rounding == "ceil":
        return _ceil_ms_to_minute(ms)
    raise ValueError(f"Invalid rounding mode: {rounding}")


def _request_json(url: str, *, timeout_seconds: int, max_retries: int) -> list:
    backoff = 1.0
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            request = Request(url, headers={"User-Agent": "buff-m1-ingest"})
            with urlopen(request, timeout=timeout_seconds) as response:
                if response.status != 200:
                    raise HTTPError(url, response.status, response.reason, response.headers, None)
                payload = response.read().decode("utf-8")
                return json.loads(payload)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == max_retries - 1:
                break
            time.sleep(backoff)
            backoff *= 2

    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to fetch klines payload.")


def _build_klines_url(symbol: str, start_ms: int, end_ms: int, limit: int) -> str:
    params = [
        ("symbol", symbol),
        ("interval", INTERVAL_1M),
        ("startTime", str(start_ms)),
        ("endTime", str(end_ms)),
        ("limit", str(limit)),
    ]
    return f"{BINANCE_FUTURES_BASE_URL}{KLINES_ENDPOINT}?{urlencode(params)}"


def fetch_klines_1m(
    symbol: str,
    start_ms: int,
    end_ms: int,
    *,
    rate_limit_sleep: float = DEFAULT_RATE_LIMIT_SLEEP,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> pd.DataFrame:
    """Fetch 1m klines for a single symbol from Binance Futures.

    Args:
        symbol: Binance symbol (e.g., "BTCUSDT").
        start_ms: Inclusive start timestamp (UTC ms, minute-aligned).
        end_ms: Exclusive end timestamp (UTC ms, minute-aligned).
        rate_limit_sleep: Sleep seconds between requests.
        max_retries: Max HTTP retries per request.
        timeout_seconds: HTTP timeout in seconds.

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume.
    """
    if not symbol:
        raise ValueError("symbol is required")
    if end_ms <= start_ms:
        return pd.DataFrame(columns=OUTPUT_COLUMNS[:-1])

    rows: list[list[int | float]] = []
    pointer = start_ms

    while pointer < end_ms:
        chunk_end = min(end_ms - 1, pointer + (KLINES_LIMIT * MS_PER_MINUTE) - 1)
        url = _build_klines_url(symbol, pointer, chunk_end, KLINES_LIMIT)
        payload = _request_json(url, timeout_seconds=timeout_seconds, max_retries=max_retries)

        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected response payload for {symbol}: {payload}")
        if not payload:
            break

        for entry in payload:
            open_time = int(entry[0])
            if open_time < start_ms or open_time >= end_ms:
                continue
            rows.append(
                [
                    _floor_ms_to_minute(open_time),
                    float(entry[1]),
                    float(entry[2]),
                    float(entry[3]),
                    float(entry[4]),
                    float(entry[5]),
                ]
            )

        last_open = int(payload[-1][0])
        next_pointer = last_open + MS_PER_MINUTE
        if next_pointer <= pointer:
            break
        pointer = next_pointer
        time.sleep(rate_limit_sleep)

    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS[:-1])
    return df


def download_ohlcv_1m(
    symbols: Sequence[str],
    start_time: str | datetime | int,
    end_time: str | datetime | int,
    *,
    rate_limit_sleep: float = DEFAULT_RATE_LIMIT_SLEEP,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> pd.DataFrame:
    """Download 1m OHLCV data for multiple symbols.

    Args:
        symbols: Iterable of Binance symbols.
        start_time: Inclusive UTC start time (ISO-8601, datetime, or ms int).
        end_time: Exclusive UTC end time (ISO-8601, datetime, or ms int).
        rate_limit_sleep: Sleep seconds between requests.
        max_retries: Max HTTP retries per request.
        timeout_seconds: HTTP timeout in seconds.

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume, symbol.
    """
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        cleaned = _normalize_symbol(symbol)
        if cleaned and cleaned not in seen:
            normalized.append(cleaned)
            seen.add(cleaned)

    if not normalized:
        raise ValueError("At least one symbol is required.")

    start_ms = _parse_time_to_utc_ms(start_time, rounding="floor")
    end_ms = _parse_time_to_utc_ms(end_time, rounding="ceil")

    if end_ms <= start_ms:
        raise ValueError("end_time must be after start_time.")

    frames: list[pd.DataFrame] = []
    for symbol in normalized:
        df = fetch_klines_1m(
            symbol,
            start_ms,
            end_ms,
            rate_limit_sleep=rate_limit_sleep,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )
        df["symbol"] = symbol
        frames.append(df)

    if frames:
        combined = pd.concat(frames, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=OUTPUT_COLUMNS)

    combined = combined[OUTPUT_COLUMNS]
    if not combined.empty:
        combined["timestamp"] = combined["timestamp"].astype("int64")
        for col in ["open", "high", "low", "close", "volume"]:
            combined[col] = combined[col].astype("float64")
        combined["symbol"] = combined["symbol"].astype("string")
        combined = combined.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    return combined
