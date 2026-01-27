"""Verify data quality report against actual data."""

import json
from pathlib import Path

import pandas as pd

from buff.data.store import load_parquet, symbol_to_filename
from buff.data.validate import expected_step_seconds


def verify_outputs() -> None:
    """Verify reports/data_quality.json against saved parquet files.

    Checks that:
    - zero_volume_bars_count matches actual count
    - duplicates_count matches actual count
    - gap_ranges do not include timestamps present in data
    """
    report_path = Path("reports/data_quality.json")
    data_dir = Path("data/clean")

    if not report_path.exists():
        print(f"ERROR: Report not found: {report_path}")
        return

    with open(report_path, "r") as f:
        report = json.load(f)

    verified_count = 0
    errors = []

    per_symbol = report.get("per_symbol", [])
    if not isinstance(per_symbol, list):
        print("ERROR: Report format invalid: expected per_symbol list.")
        return

    for metrics in per_symbol:
        symbol = metrics.get("symbol")
        timeframe = metrics.get("timeframe")
        if not symbol or not timeframe:
            errors.append("ERROR: Report entry missing symbol/timeframe")
            continue

        filename = symbol_to_filename(symbol, timeframe)
        filepath = data_dir / filename
        if not filepath.exists():
            errors.append(f"ERROR: {symbol}: parquet file not found at {filepath}")
            continue

        try:
            df = load_parquet(str(filepath))
        except Exception as e:
            errors.append(f"ERROR: {symbol}: failed to load parquet: {e}")
            continue

        zero_volume_expected = int(metrics.get("zero_volume_bars_count", -1))
        zero_volume_actual = int((df["volume"] <= 0).sum())
        if zero_volume_expected != zero_volume_actual:
            errors.append(
                f"ERROR: {symbol}: zero_volume_bars_count mismatch "
                f"(report={zero_volume_expected}, actual={zero_volume_actual})"
            )

        duplicates_expected = int(metrics.get("duplicates_count", -1))
        duplicates_actual = int(df["ts"].duplicated().sum())
        if duplicates_expected != duplicates_actual:
            errors.append(
                f"ERROR: {symbol}: duplicates_count mismatch "
                f"(report={duplicates_expected}, actual={duplicates_actual})"
            )

        gap_ranges = metrics.get("gap_ranges", [])
        step_seconds = expected_step_seconds(timeframe)
        for gap in gap_ranges:
            start = pd.Timestamp(gap["start"])
            end = pd.Timestamp(gap["end"])
            expected = int(gap["missing_bars"])
            if end < start:
                errors.append(f"ERROR: {symbol}: invalid gap range {start} > {end}")
                continue

            missing_ts = pd.date_range(start, end, freq=f"{step_seconds}s", tz="UTC")
            if len(missing_ts) != expected:
                errors.append(
                    f"ERROR: {symbol}: gap missing_bars mismatch "
                    f"(report={expected}, computed={len(missing_ts)})"
                )
            if df["ts"].isin(missing_ts).any():
                errors.append(f"ERROR: {symbol}: gap range contains existing timestamps")

        verified_count += 1

    if errors:
        for err in errors:
            print(err)
        print(f"ERROR: Verification failed with {len(errors)} error(s)")
    else:
        print(f"OK: verified {verified_count} symbol(s)")


if __name__ == "__main__":
    verify_outputs()
