"""1m OHLCV ingestion from Binance USDT-M Futures klines."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from .store import write_parquet_1m
from .validate import DataValidationError, validate_1m

BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"
KLINES_ENDPOINT = "/fapi/v1/klines"
INTERVAL_1M = "1m"
KLINES_LIMIT = 1500
MS_PER_MINUTE = 60_000
RATE_LIMIT_SLEEP = 0.1

LOGGER = logging.getLogger(__name__)


def _normalize_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if "/" in cleaned:
        cleaned = cleaned.replace("/", "")
    return cleaned


def _parse_iso8601_to_ms(value: str) -> int:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware (use Z).")
    return int(dt.astimezone(timezone.utc).timestamp() * 1000)


def _ms_to_iso8601(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _utc_now_floor_minute_ms() -> int:
    now = datetime.now(timezone.utc)
    floored = now.replace(second=0, microsecond=0)
    return int(floored.timestamp() * 1000)


def _request_json(url: str, timeout_seconds: int, max_retries: int) -> Any:
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
    if last_error:
        raise last_error
    raise RuntimeError("Failed to fetch JSON payload.")


def _build_klines_url(symbol: str, start_ms: int, end_ms: int, limit: int = KLINES_LIMIT) -> str:
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
    max_retries: int = 5,
    timeout_seconds: int = 30,
) -> pd.DataFrame:
    """Fetch 1m klines for a symbol from Binance Futures.

    Args:
        symbol: Binance symbol (e.g., "BTCUSDT").
        start_ms: Inclusive start timestamp in ms.
        end_ms: Exclusive end timestamp in ms.
        max_retries: Max HTTP retries per request.
        timeout_seconds: HTTP timeout in seconds.

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume.
    """
    if end_ms <= start_ms:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    rows: list[list[float | int]] = []
    pointer = start_ms
    while pointer < end_ms:
        chunk_end = min(end_ms - 1, pointer + (KLINES_LIMIT * MS_PER_MINUTE) - 1)
        url = _build_klines_url(symbol, pointer, chunk_end, KLINES_LIMIT)
        payload = _request_json(url, timeout_seconds=timeout_seconds, max_retries=max_retries)
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected response for {symbol}: {payload}")
        if not payload:
            break
        for entry in payload:
            open_time = int(entry[0])
            if open_time < start_ms or open_time >= end_ms:
                continue
            rows.append(
                [
                    open_time,
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
        time.sleep(RATE_LIMIT_SLEEP)

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return df


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, sort_keys=True, indent=2)
        handle.write("\n")


def ingest(
    symbols: list[str],
    since: str,
    end: str | None,
    out_dir: Path,
    report_path: Path | None,
    *,
    timeframe: str = INTERVAL_1M,
    max_retries: int = 5,
    timeout_seconds: int = 30,
) -> None:
    """Ingest 1m OHLCV data for symbols and write parquet + report."""
    if timeframe != INTERVAL_1M:
        raise ValueError("Only timeframe=1m is supported for M1.")

    normalized = []
    seen = set()
    for symbol in symbols:
        cleaned = _normalize_symbol(symbol)
        if cleaned and cleaned not in seen:
            normalized.append(cleaned)
            seen.add(cleaned)
    if not normalized:
        raise ValueError("At least one symbol is required.")

    start_ms = _parse_iso8601_to_ms(since)
    end_ms = _parse_iso8601_to_ms(end) if end else _utc_now_floor_minute_ms()

    if start_ms % MS_PER_MINUTE != 0 or end_ms % MS_PER_MINUTE != 0:
        raise ValueError("since/end must be aligned to exact minute boundaries.")
    if end_ms <= start_ms:
        raise ValueError("end must be after since.")

    expected_rows = (end_ms - start_ms) // MS_PER_MINUTE
    by_symbol: dict[str, dict[str, Any]] = {}
    parquet_files: list[str] = []
    errors: list[str] = []

    for symbol in normalized:
        try:
            LOGGER.info(
                "Fetching %s %s -> %s", symbol, _ms_to_iso8601(start_ms), _ms_to_iso8601(end_ms)
            )
            df = fetch_klines_1m(
                symbol, start_ms, end_ms, max_retries=max_retries, timeout_seconds=timeout_seconds
            )
            df.insert(0, "symbol", symbol)
            stats = validate_1m(df, symbol, start_ms, end_ms)
            out_path = write_parquet_1m(df, out_dir, symbol)
            parquet_files.append(str(out_path))
            by_symbol[symbol] = {
                "rows": stats["rows"],
                "expected_rows": expected_rows,
                "missing_ratio": stats["missing_ratio"],
                "duplicates": stats["duplicates_count"],
                "gaps": stats["gaps_count"],
                "zero_volume_rows": stats["zero_volume_rows"],
                "misaligned_rows": stats["misaligned_rows"],
                "integrity_violations_count": stats["integrity_violations_count"],
                "start_timestamp": stats["start_timestamp"],
                "end_timestamp": stats["end_timestamp"],
                "validated": True,
            }
        except DataValidationError as exc:
            errors.append(f"{symbol}: {exc}")
            stats = exc.stats or {}
            by_symbol[symbol] = {
                "rows": stats.get("rows", 0),
                "expected_rows": expected_rows,
                "missing_ratio": stats.get("missing_ratio", 1.0),
                "duplicates": stats.get("duplicates_count", 0),
                "gaps": stats.get("gaps_count", expected_rows),
                "zero_volume_rows": stats.get("zero_volume_rows", 0),
                "misaligned_rows": stats.get("misaligned_rows", 0),
                "integrity_violations_count": stats.get("integrity_violations_count", 0),
                "start_timestamp": stats.get("start_timestamp"),
                "end_timestamp": stats.get("end_timestamp"),
                "validated": False,
                "error": str(exc),
            }
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{symbol}: {exc}")
            by_symbol[symbol] = {
                "rows": 0,
                "expected_rows": expected_rows,
                "missing_ratio": 1.0 if expected_rows else 0.0,
                "duplicates": 0,
                "gaps": expected_rows,
                "zero_volume_rows": 0,
                "misaligned_rows": 0,
                "integrity_violations_count": 0,
                "start_timestamp": None,
                "end_timestamp": None,
                "validated": False,
                "error": str(exc),
            }

    overall_rows = sum(entry["rows"] for entry in by_symbol.values())
    overall_duplicates = sum(entry.get("duplicates", 0) for entry in by_symbol.values())
    overall_gaps = sum(entry.get("gaps", 0) for entry in by_symbol.values())
    total_expected = expected_rows * len(normalized)
    overall_missing_ratio = (overall_gaps / total_expected) if total_expected else 0.0
    validated_all = not errors

    report = {
        "timeframe": INTERVAL_1M,
        "since": _ms_to_iso8601(start_ms),
        "end": _ms_to_iso8601(end_ms),
        "symbols": normalized,
        "overall": {
            "rows": overall_rows,
            "expected_rows": total_expected,
            "missing_ratio": overall_missing_ratio,
            "duplicates": overall_duplicates,
            "gaps": overall_gaps,
            "validated": validated_all,
        },
        "by_symbol": by_symbol,
        "artifacts": {
            "out_dir": str(out_dir),
            "parquet_files": sorted(parquet_files),
        },
    }

    if errors:
        report["overall"]["error"] = "; ".join(errors)

    if report_path:
        _write_report(report_path, report)

    if errors:
        summary = "; ".join(errors)
        raise DataValidationError(f"Validation failed for symbols: {summary}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest Binance Futures 1m OHLCV data.")
    parser.add_argument(
        "--symbols", nargs="+", required=True, help="Symbols (e.g., BTCUSDT ETHUSDT)."
    )
    parser.add_argument(
        "--since", required=True, help="ISO-8601 start (inclusive), e.g. 2024-01-01T00:00:00Z"
    )
    parser.add_argument(
        "--end", default=None, help="ISO-8601 end (exclusive), e.g. 2024-01-02T00:00:00Z"
    )
    parser.add_argument("--timeframe", default=INTERVAL_1M, help="Only 1m is supported.")
    parser.add_argument("--out", default="data", help="Output directory (default: data).")
    parser.add_argument(
        "--report",
        default="reports/data_quality.json",
        help="Report output path (default: reports/data_quality.json).",
    )
    parser.add_argument("--max-retries", type=int, default=5, help="HTTP max retries (default: 5).")
    parser.add_argument(
        "--timeout-seconds", type=int, default=30, help="HTTP timeout seconds (default: 30)."
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report_path = Path(args.report) if args.report else None
    try:
        ingest(
            symbols=args.symbols,
            since=args.since,
            end=args.end,
            out_dir=Path(args.out),
            report_path=report_path,
            timeframe=args.timeframe,
            max_retries=args.max_retries,
            timeout_seconds=args.timeout_seconds,
        )
    except DataValidationError as exc:
        LOGGER.error(str(exc))
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Ingest failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
