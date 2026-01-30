"""Deterministic data quality reporting for OHLCV parquet files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from buff.data.store import load_parquet, ohlcv_parquet_path
from buff.data.validate import calendar_freq


REQUIRED_COLUMNS = ("ts", "open", "high", "low", "close", "volume")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_symbol(symbol: str) -> str:
    if "/" in symbol:
        return symbol
    if symbol.endswith("USDT") and len(symbol) > 4:
        return f"{symbol[:-4]}/USDT"
    return symbol


def _discover_timeframes(data_dir: Path) -> list[str]:
    return sorted(
        path.name.split("=", 1)[1]
        for path in data_dir.glob("timeframe=*")
        if path.is_dir() and "=" in path.name
    )


def _discover_symbols(data_dir: Path, timeframe: str) -> list[str]:
    symbol_dirs = sorted((data_dir / f"timeframe={timeframe}").glob("symbol=*"))
    symbols = []
    for path in symbol_dirs:
        symbols.append(path.name.split("=", 1)[1])
    return symbols


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if "ts" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["ts"]):
        df = df.copy()
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values("ts").reset_index(drop=True)


def _fixed_freq(timeframe: str) -> str:
    if timeframe.endswith("m"):
        minutes = int(timeframe[:-1])
        return f"{minutes}min"
    if timeframe.endswith("h"):
        hours = int(timeframe[:-1])
        return f"{hours}h"
    if timeframe.endswith("d"):
        days = int(timeframe[:-1])
        return f"{days}D"
    if timeframe == "1w":
        return "W-MON"
    if timeframe == "2w":
        return "2W-MON"
    raise ValueError(f"Unknown fixed timeframe: {timeframe}")


def _expected_index(first_ts: pd.Timestamp, last_ts: pd.Timestamp, timeframe: str) -> pd.DatetimeIndex:
    freq = calendar_freq(timeframe)
    if freq:
        return pd.date_range(first_ts, last_ts, freq=freq, tz="UTC")
    return pd.date_range(first_ts, last_ts, freq=_fixed_freq(timeframe), tz="UTC")


def _gap_ranges_from_expected(
    expected: pd.DatetimeIndex, actual_set: set[pd.Timestamp]
) -> tuple[list[dict], int]:
    gaps = []
    missing_total = 0
    current = []

    for ts in expected:
        if ts not in actual_set:
            current.append(ts)
        else:
            if current:
                gaps.append(
                    {
                        "start": current[0].isoformat(),
                        "end": current[-1].isoformat(),
                        "missing_bars": len(current),
                    }
                )
                missing_total += len(current)
                current = []

    if current:
        gaps.append(
            {
                "start": current[0].isoformat(),
                "end": current[-1].isoformat(),
                "missing_bars": len(current),
            }
        )
        missing_total += len(current)

    return gaps, missing_total


def _validate_required_columns(df: pd.DataFrame, symbol: str, timeframe: str) -> None:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"{symbol} {timeframe} missing required columns: {missing}")


def _build_symbol_report(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    checksum: str,
    strict: bool,
) -> dict:
    df = _normalize_df(df)
    _validate_required_columns(df, symbol, timeframe)

    rows_total = int(len(df))
    if rows_total == 0:
        first_ts = ""
        last_ts = ""
        expected_bars_count = 0
        gaps, missing_bars_count = [], 0
    else:
        first_ts = df["ts"].iloc[0].isoformat()
        last_ts = df["ts"].iloc[-1].isoformat()
        expected = _expected_index(df["ts"].iloc[0], df["ts"].iloc[-1], timeframe)
        actual_set = set(df["ts"])
        expected_bars_count = len(expected)
        gaps, missing_bars_count = _gap_ranges_from_expected(expected, actual_set)

    duplicates_count = int(df["ts"].duplicated().sum())
    zero_volume_bars_count = int((df["volume"] <= 0).sum())

    price_cols = ["open", "high", "low", "close"]
    high_lt_low_count = int((df["high"] < df["low"]).sum())
    negative_price_count = int((df[price_cols] < 0).any(axis=1).sum())
    nan_count = int(df[price_cols + ["volume"]].isna().any(axis=1).sum())

    if strict and (nan_count > 0 or negative_price_count > 0):
        raise ValueError(
            f"{symbol} {timeframe} invalid OHLCV: nan_count={nan_count}, "
            f"negative_price_count={negative_price_count}"
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
    timeframes: Iterable[str] | None,
    strict: bool = True,
) -> dict:
    if timeframes is None:
        timeframes_list = _discover_timeframes(data_dir)
    else:
        timeframes_list = list(timeframes)

    if symbols is None:
        symbols_list = []
    else:
        symbols_list = [_normalize_symbol(sym) for sym in symbols]

    per_symbol = []
    global_gap_ranges = []

    for timeframe in sorted(set(timeframes_list)):
        if symbols_list:
            tf_symbols = sorted(set(symbols_list))
        else:
            tf_symbols = sorted(set(_discover_symbols(data_dir, timeframe)))
            tf_symbols = [_normalize_symbol(sym) for sym in tf_symbols]

        for symbol in tf_symbols:
            path = ohlcv_parquet_path(data_dir, symbol, timeframe)
            if not path.exists():
                raise FileNotFoundError(f"Missing parquet for {symbol} {timeframe}: {path}")
            df = load_parquet(str(path))
            checksum = _sha256_file(path)
            report = _build_symbol_report(df, symbol, timeframe, checksum, strict=strict)
            per_symbol.append(report)
            for gap in report["gap_ranges"]:
                global_gap_ranges.append(
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "start": gap["start"],
                        "end": gap["end"],
                        "missing_bars": gap["missing_bars"],
                    }
                )

    per_symbol = sorted(per_symbol, key=lambda item: (item["symbol"], item["timeframe"]))

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
        "timeframe": "ALL",
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
        "timeframes": sorted(set(timeframes_list)),
        "symbols": sorted(set(symbols_list)) if symbols_list else sorted(
            {item["symbol"] for item in per_symbol}
        ),
        "global": global_report,
        "per_symbol": per_symbol,
    }


def write_report(report: dict, out_path: Path) -> None:
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
    parser.add_argument(
        "--timeframes",
        type=str,
        default="",
        help="Comma-separated timeframes. If omitted, auto-detect.",
    )
    parser.add_argument(
        "--data_dir",
        type=str,
        required=True,
        help="Base directory containing parquet files.",
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
    timeframes = None
    if args.symbols:
        symbols = [sym.strip() for sym in args.symbols.split(",") if sym.strip()]
    if args.timeframes:
        timeframes = [tf.strip() for tf in args.timeframes.split(",") if tf.strip()]

    data_dir = Path(args.data_dir)
    out_path = Path(args.out)
    report = build_report(data_dir, symbols, timeframes, strict=not args.no_strict)
    write_report(report, out_path)


if __name__ == "__main__":
    main()
