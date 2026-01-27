"""Deterministic data quality reporting for OHLCV parquet files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from buff.data.store import load_parquet, symbol_to_filename
from buff.data.validate import expected_step_seconds


REQUIRED_COLUMNS = ("ts", "open", "high", "low", "close", "volume")


def _sha256_file(path: Path) -> str:
    """Return SHA256 checksum for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _filename_to_symbol(filename: str, timeframe: str) -> str:
    """Convert parquet filename to symbol."""
    suffix = f"_{timeframe}.parquet"
    if not filename.endswith(suffix):
        raise ValueError(f"Unexpected filename format: {filename}")
    symbol_part = filename[: -len(suffix)]
    return symbol_part.replace("_", "/")


def _normalize_symbol(symbol: str) -> str:
    """Normalize symbols to CCXT-style (e.g., BTC/USDT)."""
    if "/" in symbol:
        return symbol
    if symbol.endswith("USDT") and len(symbol) > 4:
        return f"{symbol[:-4]}/USDT"
    return symbol


def _iter_symbol_files(data_dir: Path, symbols: Iterable[str], timeframe: str) -> list[Path]:
    """Resolve parquet file paths for given symbols."""
    paths = []
    for symbol in symbols:
        normalized = _normalize_symbol(symbol)
        filename = symbol_to_filename(normalized, timeframe)
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing parquet for {normalized}: {path}")
        paths.append(path)
    return paths


def _discover_symbols(data_dir: Path, timeframe: str) -> list[str]:
    """Discover symbols from parquet filenames in data_dir."""
    files = sorted(data_dir.glob(f"*_{timeframe}.parquet"))
    symbols = []
    for path in files:
        symbols.append(_filename_to_symbol(path.name, timeframe))
    return symbols


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure dataframe is sorted by timestamp and ts is UTC."""
    if "ts" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["ts"]):
        df = df.copy()
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values("ts").reset_index(drop=True)


def _gap_ranges(ts_series: pd.Series, step_seconds: int) -> tuple[list[dict], int]:
    """Compute gap ranges and total missing bars."""
    gaps = []
    missing_total = 0
    if ts_series.empty:
        return gaps, missing_total

    diffs = ts_series.diff().dt.total_seconds()
    for idx, diff in enumerate(diffs.iloc[1:], start=1):
        if pd.isna(diff):
            continue
        if diff > step_seconds:
            missing = int((diff / step_seconds) - 1)
            prev_ts = ts_series.iloc[idx - 1]
            next_ts = ts_series.iloc[idx]
            start = prev_ts + pd.Timedelta(seconds=step_seconds)
            end = next_ts - pd.Timedelta(seconds=step_seconds)
            gaps.append(
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "missing_bars": missing,
                }
            )
            missing_total += missing
    return gaps, missing_total


def _expected_bars_count(first_ts: pd.Timestamp, last_ts: pd.Timestamp, step_seconds: int) -> int:
    """Compute expected bar count between two timestamps (inclusive)."""
    total_seconds = (last_ts - first_ts).total_seconds()
    if total_seconds < 0:
        return 0
    return int(total_seconds // step_seconds) + 1


def _validate_required_columns(df: pd.DataFrame, symbol: str) -> None:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"{symbol} missing required columns: {missing}")


def _build_symbol_report(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    checksum: str,
    strict: bool,
) -> dict:
    df = _normalize_df(df)
    _validate_required_columns(df, symbol)

    rows_total = int(len(df))
    if rows_total == 0:
        first_ts = ""
        last_ts = ""
        expected_bars_count = 0
        gaps, missing_bars_count = [], 0
    else:
        first_ts = df["ts"].iloc[0].isoformat()
        last_ts = df["ts"].iloc[-1].isoformat()
        step_seconds = expected_step_seconds(timeframe)
        expected_bars_count = _expected_bars_count(df["ts"].iloc[0], df["ts"].iloc[-1], step_seconds)
        gaps, missing_bars_count = _gap_ranges(df["ts"], step_seconds)

    duplicates_count = int(df["ts"].duplicated().sum())
    zero_volume_bars_count = int((df["volume"] <= 0).sum())

    price_cols = ["open", "high", "low", "close"]
    high_lt_low_count = int((df["high"] < df["low"]).sum())
    negative_price_count = int((df[price_cols] < 0).any(axis=1).sum())
    nan_count = int(df[price_cols + ["volume"]].isna().any(axis=1).sum())

    if strict and (nan_count > 0 or negative_price_count > 0):
        raise ValueError(
            f"{symbol} invalid OHLCV: nan_count={nan_count}, negative_price_count={negative_price_count}"
        )

    missing_ratio = (
        round(missing_bars_count / expected_bars_count, 8) if expected_bars_count > 0 else 0.0
    )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "rows_total": rows_total,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "expected_bars_count": expected_bars_count,
        "missing_bars_count": missing_bars_count,
        "missing_ratio": missing_ratio,
        "gaps_count": len(gaps),
        "gap_ranges": gaps,
        "duplicates_count": duplicates_count,
        "zero_volume_bars_count": zero_volume_bars_count,
        "high_lt_low_count": high_lt_low_count,
        "negative_price_count": negative_price_count,
        "nan_count": nan_count,
        "sha256": checksum,
    }


def build_report(
    data_dir: Path,
    symbols: Iterable[str] | None,
    timeframe: str,
    strict: bool = True,
) -> dict:
    """Build a deterministic data quality report for OHLCV parquet files."""
    if symbols is None:
        symbols_list = _discover_symbols(data_dir, timeframe)
    else:
        symbols_list = [_normalize_symbol(sym) for sym in symbols]

    symbols_list = sorted(set(symbols_list))
    files = _iter_symbol_files(data_dir, symbols_list, timeframe)

    per_symbol = []
    global_gap_ranges = []
    for symbol, path in zip(symbols_list, files):
        df = load_parquet(str(path))
        checksum = _sha256_file(path)
        report = _build_symbol_report(df, symbol, timeframe, checksum, strict=strict)
        per_symbol.append(report)
        for gap in report["gap_ranges"]:
            global_gap_ranges.append(
                {
                    "symbol": symbol,
                    "start": gap["start"],
                    "end": gap["end"],
                    "missing_bars": gap["missing_bars"],
                }
            )

    rows_total = sum(item["rows_total"] for item in per_symbol)
    expected_bars_total = sum(item["expected_bars_count"] for item in per_symbol)
    missing_bars_total = sum(item["missing_bars_count"] for item in per_symbol)
    gaps_count_total = sum(item["gaps_count"] for item in per_symbol)
    duplicates_total = sum(item["duplicates_count"] for item in per_symbol)
    zero_volume_total = sum(item["zero_volume_bars_count"] for item in per_symbol)
    high_lt_low_total = sum(item["high_lt_low_count"] for item in per_symbol)
    negative_price_total = sum(item["negative_price_count"] for item in per_symbol)
    nan_total = sum(item["nan_count"] for item in per_symbol)

    first_ts_vals = [item["first_ts"] for item in per_symbol if item["first_ts"]]
    last_ts_vals = [item["last_ts"] for item in per_symbol if item["last_ts"]]
    first_ts = min(first_ts_vals) if first_ts_vals else ""
    last_ts = max(last_ts_vals) if last_ts_vals else ""

    combined_checksum_source = "|".join(item["sha256"] for item in per_symbol)
    global_checksum = hashlib.sha256(combined_checksum_source.encode("utf-8")).hexdigest()

    global_report = {
        "symbol": "ALL",
        "timeframe": timeframe,
        "rows_total": rows_total,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "expected_bars_count": expected_bars_total,
        "missing_bars_count": missing_bars_total,
        "missing_ratio": round(missing_bars_total / expected_bars_total, 8)
        if expected_bars_total > 0
        else 0.0,
        "gaps_count": gaps_count_total,
        "gap_ranges": global_gap_ranges,
        "duplicates_count": duplicates_total,
        "zero_volume_bars_count": zero_volume_total,
        "high_lt_low_count": high_lt_low_total,
        "negative_price_count": negative_price_total,
        "nan_count": nan_total,
        "sha256": global_checksum,
    }

    return {
        "timeframe": timeframe,
        "symbols": symbols_list,
        "global": global_report,
        "per_symbol": per_symbol,
    }


def write_report(report: dict, out_path: Path) -> None:
    """Write report deterministically to JSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic OHLCV data quality report.")
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="Comma-separated symbols (e.g., BTCUSDT,ETHUSDT). If omitted, auto-detect.",
    )
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe (e.g., 1h)")
    parser.add_argument(
        "--data_dir",
        type=str,
        required=True,
        help="Directory containing parquet files.",
    )
    parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Output path for data_quality.json",
    )
    parser.add_argument(
        "--no_strict",
        action="store_true",
        help="Do not fail on NaNs or negative prices.",
    )

    args = parser.parse_args()
    symbols = None
    if args.symbols:
        symbols = [sym.strip() for sym in args.symbols.split(",") if sym.strip()]

    data_dir = Path(args.data_dir)
    out_path = Path(args.out)
    report = build_report(data_dir, symbols, args.timeframe, strict=not args.no_strict)
    write_report(report, out_path)


if __name__ == "__main__":
    main()
