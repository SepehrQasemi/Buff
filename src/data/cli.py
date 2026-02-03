"""CLI for deterministic Binance Futures OHLCV ingestion and aggregation (M1)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from buff.features.bundle import compute_features, write_feature_bundle
from buff.features.contract import build_feature_specs_from_registry
from buff.features.metadata import build_source_fingerprint, get_git_sha, sha256_file
from buff.features.registry import FEATURES
from .aggregate import aggregate_ohlcv
from .ingest import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RATE_LIMIT_SLEEP,
    DEFAULT_TIMEOUT_SECONDS,
    download_ohlcv_1m,
)
from .store import write_parquet
from .validate import (
    DataValidationError,
    check_monotonic_timestamp,
    check_no_duplicates,
    check_non_negative_volume,
)

MS_PER_MINUTE = 60_000


def _normalize_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if "/" in cleaned:
        cleaned = cleaned.replace("/", "")
    return cleaned


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output


def _normalize_timeframe_label(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned.endswith("min"):
        cleaned = cleaned[:-3] + "m"
    return cleaned


def _freq_ms(timeframe: str) -> int:
    delta = pd.to_timedelta(timeframe)
    ms = int(delta.total_seconds() * 1000)
    if ms <= 0:
        raise ValueError(f"Invalid timeframe: {timeframe}")
    if ms % MS_PER_MINUTE != 0:
        raise ValueError("Timeframe must be a whole number of minutes.")
    return ms


def _floor_ms_to_minute(ms: int) -> int:
    return (ms // MS_PER_MINUTE) * MS_PER_MINUTE


def _ceil_ms_to_minute(ms: int) -> int:
    if ms % MS_PER_MINUTE == 0:
        return ms
    return ((ms // MS_PER_MINUTE) + 1) * MS_PER_MINUTE


def _is_date_only(text: str) -> bool:
    return "T" not in text and " " not in text


def _parse_utc_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _parse_time_range(since: str, until: str) -> tuple[int, int, str, str]:
    since_dt = _parse_utc_datetime(since)
    until_dt = _parse_utc_datetime(until)

    if _is_date_only(until):
        until_dt = until_dt + timedelta(days=1)

    start_ms = _floor_ms_to_minute(int(since_dt.timestamp() * 1000))
    end_ms = _ceil_ms_to_minute(int(until_dt.timestamp() * 1000))

    if end_ms <= start_ms:
        raise ValueError("until must be after since.")

    return start_ms, end_ms, _ms_to_iso(start_ms), _ms_to_iso(end_ms)


def _ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _quality_metrics(
    df: pd.DataFrame,
    *,
    start_ms: int,
    end_ms: int,
    freq_ms: int,
) -> tuple[int, int, float, int | None, int | None]:
    if end_ms <= start_ms:
        return 0, 0, 0.0, None, None

    first_bin = (start_ms // freq_ms) * freq_ms
    last_bin = ((end_ms - 1) // freq_ms) * freq_ms
    expected = ((last_bin - first_bin) // freq_ms) + 1

    if df.empty:
        missing_count = expected
        missing_pct = 0.0 if expected == 0 else (missing_count / expected) * 100.0
        return 0, missing_count, missing_pct, None, None

    unique_count = int(df["timestamp"].drop_duplicates().shape[0])
    missing_count = max(expected - unique_count, 0)
    missing_pct = 0.0 if expected == 0 else (missing_count / expected) * 100.0

    start_ts = int(df["timestamp"].min())
    end_ts = int(df["timestamp"].max())
    return unique_count, missing_count, missing_pct, start_ts, end_ts


def _build_quality_entry(
    df: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
    freq_ms: int,
) -> dict[str, object]:
    rows = int(df.shape[0])
    duplicates = int(df.duplicated(subset=["timestamp"], keep="first").sum())
    zero_volume_rows = 0
    if not df.empty:
        zero_volume_rows = int((df["volume"].astype("float64") == 0).sum())
    _, missing_count, missing_pct, start_ts, end_ts = _quality_metrics(
        df, start_ms=start_ms, end_ms=end_ms, freq_ms=freq_ms
    )
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "rows": rows,
        "missing_percentage": round(missing_pct, 6),
        "missing_count": int(missing_count),
        "duplicate_count": duplicates,
        "zero_volume_rows": zero_volume_rows,
        "start_timestamp": _ms_to_iso(start_ts),
        "end_timestamp": _ms_to_iso(end_ts),
    }


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, sort_keys=True, indent=2)
        handle.write("\n")


def _run_ingest(args: argparse.Namespace) -> None:
    symbols = _dedupe_preserve_order(_normalize_symbol(s) for s in args.symbols)
    if not symbols:
        raise ValueError("At least one symbol is required.")

    timeframes = _dedupe_preserve_order(_normalize_timeframe_label(t) for t in args.timeframes)
    if "1m" not in timeframes:
        raise ValueError("timeframes must include 1m.")

    start_ms, end_ms, since_iso, until_iso = _parse_time_range(args.since, args.until)

    df_1m = download_ohlcv_1m(
        symbols,
        start_ms,
        end_ms,
        rate_limit_sleep=args.rate_limit_sleep,
        max_retries=args.max_retries,
        timeout_seconds=args.timeout_seconds,
    )

    if not df_1m.empty:
        df_1m = df_1m.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    try:
        check_no_duplicates(df_1m, keys=["symbol", "timestamp"])
        check_monotonic_timestamp(df_1m)
        check_non_negative_volume(df_1m)
    except DataValidationError as exc:
        raise DataValidationError(f"1m validation failed: {exc}") from exc

    out_dir = Path(args.out)
    report_entries: list[dict[str, object]] = []

    for timeframe in timeframes:
        if timeframe == "1m":
            df_tf = df_1m
        else:
            df_tf = aggregate_ohlcv(df_1m, timeframe)

        df_tf = df_tf.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        freq_ms = _freq_ms(timeframe)

        for symbol in symbols:
            df_sym = df_tf[df_tf["symbol"] == symbol].reset_index(drop=True)
            write_parquet(df_sym, out_dir, symbol, timeframe)

            entry = _build_quality_entry(
                df_sym,
                symbol=symbol,
                timeframe=timeframe,
                start_ms=start_ms,
                end_ms=end_ms,
                freq_ms=freq_ms,
            )

            # Enforce missing tolerance for strict reproducibility (0.1%)
            if freq_ms == MS_PER_MINUTE and entry["missing_percentage"] > 0.1:
                raise DataValidationError(
                    f"Missing percentage exceeds 0.1% for {symbol} {timeframe}: "
                    f"{entry['missing_percentage']}%"
                )

            if entry["duplicate_count"] > 0:
                raise DataValidationError(
                    f"Duplicate rows detected for {symbol} {timeframe}: {entry['duplicate_count']}"
                )

            if args.fail_on_zero_volume and entry["zero_volume_rows"] > 0:
                raise DataValidationError(
                    f"Zero-volume rows detected for {symbol} {timeframe}: "
                    f"{entry['zero_volume_rows']}"
                )

            report_entries.append(entry)

    report_entries = sorted(report_entries, key=lambda item: (item["symbol"], item["timeframe"]))

    report = {
        "since": since_iso,
        "until": until_iso,
        "symbols": symbols,
        "timeframes": timeframes,
        "data": report_entries,
    }

    _write_report(Path(args.report), report)


def _run_features(args: argparse.Namespace) -> None:
    input_path = Path(args.input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    df = pd.read_parquet(input_path, engine="pyarrow")
    file_hashes = {str(input_path): sha256_file(input_path)}
    schema_payload = {
        "columns": [str(col) for col in df.columns],
        "dtypes": {col: str(df[col].dtype) for col in df.columns},
    }
    source_fingerprint = build_source_fingerprint(file_hashes=file_hashes, schema=schema_payload)

    df.attrs["source_paths"] = [str(input_path)]
    df.attrs["source_fingerprint"] = source_fingerprint
    df.attrs["code_fingerprint"] = get_git_sha() or "unknown"
    if args.run_id:
        df.attrs["run_id"] = str(args.run_id)
    if args.as_of_utc:
        df.attrs["as_of_utc"] = str(args.as_of_utc)

    specs = build_feature_specs_from_registry(FEATURES)
    features_frame, metadata = compute_features(df, specs)
    write_feature_bundle(args.out, features_frame, metadata)
    if args.meta_path:
        meta_path = Path(args.meta_path)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(metadata.to_dict(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic Binance Futures data pipeline.")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Ingest 1m data and aggregate higher timeframes.")
    ingest.add_argument("--symbols", nargs="+", required=True)
    ingest.add_argument("--since", required=True, help="ISO-8601 start (inclusive, UTC).")
    ingest.add_argument("--until", required=True, help="ISO-8601 end (inclusive date or UTC time).")
    ingest.add_argument("--timeframes", nargs="+", required=True)
    ingest.add_argument("--out", default="data/ohlcv", help="Output directory.")
    ingest.add_argument("--report", default="reports/data_quality.json", help="Report output path.")
    ingest.add_argument(
        "--rate-limit-sleep",
        type=float,
        default=DEFAULT_RATE_LIMIT_SLEEP,
        help="Sleep seconds between Binance requests.",
    )
    ingest.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Max HTTP retries per request.",
    )
    ingest.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds.",
    )
    ingest.add_argument(
        "--fail-on-zero-volume",
        action="store_true",
        help="Fail if any zero-volume rows are present (default: False).",
    )

    features = sub.add_parser("features", help="Compute feature bundle from 1m OHLCV parquet.")
    features.add_argument("--input", "--in", dest="input_path", required=True)
    features.add_argument("--out", required=True, help="Output directory or parquet path.")
    features.add_argument("--meta", dest="meta_path", default=None, help="Optional metadata path.")
    features.add_argument("--run-id", dest="run_id", default=None)
    features.add_argument("--as-of-utc", dest="as_of_utc", default=None)

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.command == "ingest":
        _run_ingest(args)
        return
    if args.command == "features":
        _run_features(args)
        return


if __name__ == "__main__":
    main()
