"""MVP smoke test for the M1 + M3 data pipeline (no execution logic)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype

from buff.features.bundle import compute_features, write_feature_bundle
from buff.features.contract import build_feature_specs_from_registry
from buff.features.metadata import build_source_fingerprint, get_git_sha, sha256_file
from buff.features.registry import FEATURES
from src.data.aggregate import aggregate_ohlcv
from src.data.offline_binance_ingest import download_ohlcv_1m
from src.data.store import CANONICAL_COLUMNS, write_parquet
from src.data.validate import (
    DataValidationError,
    check_missing_gaps,
    check_monotonic_timestamp,
    check_no_duplicates,
    check_non_negative_volume,
)


MS_PER_MINUTE = 60_000


@dataclass(frozen=True)
class IngestRunResult:
    out_dir: Path
    files: dict[str, Path]
    rows: int
    duration_s: float
    byte_hashes: dict[str, str]
    canonical_hashes: dict[str, str]
    byte_combined: str
    canonical_combined: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_date_only(text: str) -> bool:
    return "T" not in text and " " not in text


def _parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if "/" in cleaned:
        cleaned = cleaned.replace("/", "")
    return cleaned


def _normalize_timeframe(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned.endswith("min"):
        cleaned = cleaned[:-3] + "m"
    return cleaned


def _timeframe_ms(timeframe: str) -> int:
    delta = pd.to_timedelta(timeframe)
    ms = int(delta.total_seconds() * 1000)
    if ms <= 0:
        raise ValueError(f"Invalid timeframe: {timeframe}")
    if ms % MS_PER_MINUTE != 0:
        raise ValueError("Timeframe must be a whole number of minutes.")
    return ms


def _ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _floor_ms_to_minute(ms: int) -> int:
    return (ms // MS_PER_MINUTE) * MS_PER_MINUTE


def _ceil_ms_to_minute(ms: int) -> int:
    if ms % MS_PER_MINUTE == 0:
        return ms
    return ((ms // MS_PER_MINUTE) + 1) * MS_PER_MINUTE


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp_ms(series: pd.Series) -> pd.Series:
    if is_datetime64_any_dtype(series):
        ts = pd.to_datetime(series, utc=True)
        ns = ts.to_numpy(dtype="datetime64[ns]")
        values = (ns.astype("int64") // 1_000_000).astype("int64")
        return pd.Series(values, index=series.index, name=series.name, dtype="int64")
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError("Invalid timestamp values")
    return numeric.astype("int64")


def _canonical_hash_parquet(path: Path) -> str:
    df = pd.read_parquet(path, engine="pyarrow")
    missing = [col for col in CANONICAL_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing columns for canonical hash: {missing}")

    ordered = df[CANONICAL_COLUMNS].copy()
    ordered["timestamp"] = _timestamp_ms(ordered["timestamp"])
    for col in ["open", "high", "low", "close", "volume"]:
        ordered[col] = ordered[col].astype("float64")
    ordered["symbol"] = ordered["symbol"].astype("string")

    ordered = ordered.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
    try:
        csv_text = ordered.to_csv(index=False, line_terminator="\n")
    except TypeError:
        csv_text = ordered.to_csv(index=False, lineterminator="\n")
    payload = csv_text.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _combine_hashes(hash_map: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for key in sorted(hash_map.keys()):
        digest.update(key.encode("utf-8"))
        digest.update(b"\n")
        digest.update(hash_map[key].encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _ingest_once(
    symbols: list[str],
    *,
    timeframe: str,
    start_ms: int,
    end_ms: int,
    out_dir: Path,
) -> IngestRunResult:
    start = time.perf_counter()
    df_1m = download_ohlcv_1m(symbols, start_ms, end_ms)
    if df_1m.empty:
        raise ValueError("Ingest returned no rows.")

    df_1m = df_1m.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    if timeframe == "1m":
        df_tf = df_1m
    else:
        df_tf = aggregate_ohlcv(df_1m, timeframe)

    if df_tf.empty:
        raise ValueError(f"Aggregated {timeframe} data is empty.")

    df_tf = df_tf.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    files: dict[str, Path] = {}
    total_rows = 0
    for symbol in symbols:
        df_sym = df_tf[df_tf["symbol"] == symbol].reset_index(drop=True)
        if df_sym.empty:
            raise ValueError(f"No rows found for {symbol} at {timeframe}.")
        path = write_parquet(df_sym, out_dir, symbol, timeframe)
        files[symbol] = path
        total_rows += int(df_sym.shape[0])

    byte_hashes = {symbol: _sha256_file(path) for symbol, path in files.items()}
    canonical_hashes = {symbol: _canonical_hash_parquet(path) for symbol, path in files.items()}

    duration_s = time.perf_counter() - start
    return IngestRunResult(
        out_dir=out_dir,
        files=files,
        rows=total_rows,
        duration_s=duration_s,
        byte_hashes=byte_hashes,
        canonical_hashes=canonical_hashes,
        byte_combined=_combine_hashes(byte_hashes),
        canonical_combined=_combine_hashes(canonical_hashes),
    )


def _missing_stats(df: pd.DataFrame, freq_ms: int) -> dict[str, int | float | None]:
    if df.empty:
        return {
            "missing_count": 0,
            "expected_count": 0,
            "missing_ratio": 0.0,
            "start_timestamp": None,
            "end_timestamp": None,
        }

    timestamps = df["timestamp"].dropna().astype("int64").sort_values().drop_duplicates()
    if timestamps.empty:
        return {
            "missing_count": 0,
            "expected_count": 0,
            "missing_ratio": 0.0,
            "start_timestamp": None,
            "end_timestamp": None,
        }

    start_ts = int(timestamps.iloc[0])
    end_ts = int(timestamps.iloc[-1])
    expected = ((end_ts - start_ts) // freq_ms) + 1
    missing = max(expected - int(timestamps.shape[0]), 0)
    ratio = (missing / expected) if expected else 0.0

    return {
        "missing_count": missing,
        "expected_count": expected,
        "missing_ratio": ratio,
        "start_timestamp": start_ts,
        "end_timestamp": end_ts,
    }


def _validate_files(files: dict[str, Path], timeframe: str) -> tuple[bool, dict[str, object]]:
    details: dict[str, object] = {"per_symbol": []}
    ok = True
    freq_ms = _timeframe_ms(timeframe)

    for symbol, path in sorted(files.items()):
        df = pd.read_parquet(path, engine="pyarrow")
        df = df.copy()
        df["timestamp"] = _timestamp_ms(df["timestamp"])
        duplicates = int(df.duplicated(subset=["timestamp"], keep="first").sum())
        zero_volume_rows = int((df["volume"].astype("float64") == 0).sum()) if not df.empty else 0
        misaligned_rows = (
            int((df["timestamp"].astype("int64") % freq_ms != 0).sum()) if not df.empty else 0
        )

        gap_stats = _missing_stats(df, freq_ms)
        gap_stats_iso = {
            "missing_count": gap_stats["missing_count"],
            "expected_count": gap_stats["expected_count"],
            "missing_ratio": gap_stats["missing_ratio"],
            "start_timestamp": _ms_to_iso(gap_stats["start_timestamp"]),
            "end_timestamp": _ms_to_iso(gap_stats["end_timestamp"]),
        }

        symbol_details = {
            "symbol": symbol,
            "rows": int(df.shape[0]),
            "duplicate_count": duplicates,
            "zero_volume_rows": zero_volume_rows,
            "misaligned_rows": misaligned_rows,
            **gap_stats_iso,
        }

        try:
            check_no_duplicates(df, keys=["timestamp"])
            check_monotonic_timestamp(df)
            check_non_negative_volume(df)
            _ = check_missing_gaps(df, expected_freq=timeframe, tolerance=0.0)
        except DataValidationError as exc:
            ok = False
            symbol_details["error"] = str(exc)

        if duplicates > 0 or zero_volume_rows > 0 or misaligned_rows > 0:
            ok = False

        if isinstance(gap_stats["missing_count"], int) and gap_stats["missing_count"] > 0:
            ok = False

        details["per_symbol"].append(symbol_details)

    details["per_symbol"] = sorted(details["per_symbol"], key=lambda item: item["symbol"])
    return ok, details


def _build_features(
    input_path: Path,
    out_dir: Path,
    *,
    as_of_utc: str,
) -> tuple[Path, int]:
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
    df.attrs["as_of_utc"] = as_of_utc

    specs = build_feature_specs_from_registry(FEATURES)
    features_frame, metadata = compute_features(df, specs)
    parquet_path, _ = write_feature_bundle(out_dir, features_frame, metadata)
    return parquet_path, int(features_frame.shape[0])


def _parse_args(argv: Iterable[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MVP smoke test for M1 + M3 pipeline.")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--since", required=True, help="ISO start date (UTC).")
    parser.add_argument(
        "--until",
        default=None,
        help="Optional ISO end date/time (UTC). Defaults to last completed bar.",
    )
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--out", default="reports/mvp_smoke.json")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    started_at = _utc_now()

    symbols = [_normalize_symbol(sym) for sym in args.symbols]
    symbols = [sym for sym in symbols if sym]
    if not symbols:
        print("error: at least one symbol is required", file=sys.stderr)
        return 2

    timeframe = _normalize_timeframe(args.timeframe)
    if args.runs < 1:
        print("error: --runs must be >= 1", file=sys.stderr)
        return 2

    since_dt = _parse_iso_utc(args.since)
    if _is_date_only(args.since):
        since_dt = since_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    if args.until:
        until_dt = _parse_iso_utc(args.until)
        if _is_date_only(args.until):
            until_dt = until_dt + timedelta(days=1)
    else:
        now = _utc_now()
        freq_ms = _timeframe_ms(timeframe)
        now_ms = int(now.timestamp() * 1000)
        aligned_ms = (now_ms // freq_ms) * freq_ms
        until_dt = datetime.fromtimestamp(aligned_ms / 1000, tz=timezone.utc)

    start_ms = _floor_ms_to_minute(int(since_dt.timestamp() * 1000))
    end_ms = _ceil_ms_to_minute(int(until_dt.timestamp() * 1000))
    if end_ms <= start_ms:
        print("error: until must be after since", file=sys.stderr)
        return 2

    started_at_iso = _iso_utc(started_at)
    run_id = started_at_iso.replace(":", "").replace(".", "")
    run_root = Path("runs") / "mvp_smoke" / run_id

    report: dict[str, object] = {
        "status": "fail",
        "params": {
            "symbols": symbols,
            "timeframe": timeframe,
            "since": _iso_utc(since_dt),
            "until": _iso_utc(until_dt),
            "runs": args.runs,
            "out": str(args.out),
        },
        "ingest": {"rows": 0, "path": None, "hash": None, "duration_s": None},
        "reproducibility": {
            "runs": args.runs,
            "hashes": [],
            "stable": False,
            "hash_type": "canonical_csv_sha256",
            "stable_columns": list(CANONICAL_COLUMNS),
            "decision_method": None,
        },
        "validation": {"ok": False, "details": {}},
        "features": {"ok": False, "path": None, "rows": 0, "duration_s": None},
        "errors": [],
        "started_at_utc": started_at_iso,
        "finished_at_utc": None,
    }

    errors: list[str] = []
    ingest_runs: list[IngestRunResult] = []

    try:
        run_root.mkdir(parents=True, exist_ok=True)
        for run_idx in range(args.runs):
            out_dir = run_root / f"run_{run_idx + 1}"
            out_dir.mkdir(parents=True, exist_ok=True)
            ingest_runs.append(
                _ingest_once(
                    symbols,
                    timeframe=timeframe,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    out_dir=out_dir,
                )
            )
    except Exception as exc:
        errors.append(f"ingest_failed: {exc}")

    if ingest_runs:
        first = ingest_runs[0]
        byte_hashes = [run.byte_combined for run in ingest_runs]
        canonical_hashes = [run.canonical_combined for run in ingest_runs]
        if len(set(byte_hashes)) == 1:
            hashes = byte_hashes
            decision_method = "parquet_bytes_sha256"
        else:
            hashes = canonical_hashes
            decision_method = "canonical_csv_sha256"
        stable = len(set(hashes)) == 1

        report["ingest"] = {
            "rows": first.rows,
            "path": str(first.out_dir),
            "hash": hashes[0],
            "duration_s": round(first.duration_s, 4),
            "files": {sym: str(path) for sym, path in first.files.items()},
        }
        report["reproducibility"] = {
            "runs": args.runs,
            "hashes": hashes,
            "stable": stable,
            "hash_type": "canonical_csv_sha256",
            "stable_columns": list(CANONICAL_COLUMNS),
            "decision_method": decision_method,
        }

        if not stable:
            errors.append("reproducibility_failed: hashes_not_stable")

        validation_ok = False
        try:
            validation_ok, validation_details = _validate_files(first.files, timeframe)
            report["validation"] = {"ok": validation_ok, "details": validation_details}
            if not validation_ok:
                errors.append("validation_failed")
        except Exception as exc:
            errors.append(f"validation_failed: {exc}")

        feature_symbol = "BTCUSDT"
        if feature_symbol not in symbols:
            errors.append("features_failed: BTCUSDT not provided in --symbols")
        else:
            feature_path = first.files[feature_symbol]
            features_dir = run_root / "features"
            feature_start = time.perf_counter()
            try:
                parquet_path, rows = _build_features(
                    feature_path,
                    features_dir,
                    as_of_utc=_iso_utc(until_dt),
                )
                report["features"] = {
                    "ok": True,
                    "path": str(parquet_path),
                    "rows": rows,
                    "duration_s": round(time.perf_counter() - feature_start, 4),
                }
            except Exception as exc:
                errors.append(f"features_failed: {exc}")

    report["errors"] = errors
    report["finished_at_utc"] = _iso_utc(_utc_now())
    if not errors and ingest_runs and report["reproducibility"]["stable"]:
        report["status"] = "pass"
    else:
        report["status"] = "fail"

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    summary = "PASS" if report["status"] == "pass" else "FAIL"
    print(f"MVP_SMOKE {summary} - report: {out_path}")
    if errors:
        for item in errors:
            print(f"error: {item}", file=sys.stderr)

    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
