"""Verify data quality report against actual data."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from buff.data.store import load_parquet, ohlcv_parquet_path
from buff.data.validate import calendar_freq, expected_step_seconds


def _minimal_validate(schema: dict, payload: dict) -> list[str]:
    errors = []
    required = schema.get("required", [])
    for key in required:
        if key not in payload:
            errors.append(f"ERROR: Missing required key: {key}")

    report_required = schema.get("definitions", {}).get("report", {}).get("required", [])
    if "global" in payload:
        for key in report_required:
            if key not in payload["global"]:
                errors.append(f"ERROR: Missing required key in global: {key}")

    per_symbol = payload.get("per_symbol", [])
    if not isinstance(per_symbol, list):
        errors.append("ERROR: per_symbol must be a list")
    else:
        for item in per_symbol:
            for key in report_required:
                if key not in item:
                    errors.append(f"ERROR: Missing required key in per_symbol: {key}")
    return errors


def verify_outputs() -> None:
    """Verify reports/data_quality.json against saved parquet files.

    Checks that:
    - report schema is valid
    - requested timeframes exist for each symbol
    - duplicates and zero-volume counts match
    - gap_ranges do not include timestamps present in data
    """
    report_path = Path("reports/data_quality.json")
    data_dir = Path("data/ohlcv")
    schema_path = Path("schemas/data_quality.schema.json")
    if not schema_path.exists():
        schema_path = Path(__file__).resolve().parents[3] / "schemas" / "data_quality.schema.json"

    if not report_path.exists():
        print(f"ERROR: Report not found: {report_path}")
        return

    report = json.loads(report_path.read_text(encoding="utf-8"))

    errors = []
    if schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        try:
            import jsonschema

            jsonschema.validate(instance=report, schema=schema)
        except ModuleNotFoundError:
            errors.extend(_minimal_validate(schema, report))
        except Exception as e:
            errors.append(f"ERROR: schema validation failed: {e}")

    timeframes = report.get("timeframes", [])
    symbols = report.get("symbols", [])
    per_symbol = report.get("per_symbol", [])

    if not isinstance(per_symbol, list):
        errors.append("ERROR: Report format invalid: expected per_symbol list.")
        per_symbol = []

    reported_pairs = {(item.get("symbol"), item.get("timeframe")) for item in per_symbol}
    for symbol in symbols:
        for timeframe in timeframes:
            if (symbol, timeframe) not in reported_pairs:
                errors.append(f"ERROR: Missing report entry for {symbol} {timeframe}")

            path = ohlcv_parquet_path(data_dir, symbol, timeframe)
            if not path.exists():
                errors.append(f"ERROR: Missing parquet for {symbol} {timeframe}: {path}")

    verified_count = 0

    for metrics in per_symbol:
        symbol = metrics.get("symbol")
        timeframe = metrics.get("timeframe")
        if not symbol or not timeframe:
            errors.append("ERROR: Report entry missing symbol/timeframe")
            continue

        path = ohlcv_parquet_path(data_dir, symbol, timeframe)
        if not path.exists():
            continue

        try:
            df = load_parquet(str(path))
        except Exception as e:
            errors.append(f"ERROR: {symbol} {timeframe}: failed to load parquet: {e}")
            continue

        zero_volume_expected = int(metrics.get("zero_volume_bars_count", -1))
        zero_volume_actual = int((df["volume"] <= 0).sum())
        if zero_volume_expected != zero_volume_actual:
            errors.append(
                f"ERROR: {symbol} {timeframe}: zero_volume_bars_count mismatch "
                f"(report={zero_volume_expected}, actual={zero_volume_actual})"
            )

        duplicates_expected = int(metrics.get("duplicates_count", -1))
        duplicates_actual = int(df["ts"].duplicated().sum())
        if duplicates_expected != duplicates_actual:
            errors.append(
                f"ERROR: {symbol} {timeframe}: duplicates_count mismatch "
                f"(report={duplicates_expected}, actual={duplicates_actual})"
            )

        gap_ranges = metrics.get("gap_ranges", [])
        freq = calendar_freq(timeframe)
        step_seconds = None
        if not freq:
            try:
                step_seconds = expected_step_seconds(timeframe)
            except Exception:
                step_seconds = None

        for gap in gap_ranges:
            start = pd.Timestamp(gap["start"])
            end = pd.Timestamp(gap["end"])
            expected = int(gap["missing_bars"])
            if end < start:
                errors.append(f"ERROR: {symbol} {timeframe}: invalid gap range {start} > {end}")
                continue

            if freq:
                missing_ts = pd.date_range(start, end, freq=freq, tz="UTC")
            elif step_seconds:
                missing_ts = pd.date_range(start, end, freq=f"{step_seconds}s", tz="UTC")
            else:
                missing_ts = pd.DatetimeIndex([start])

            if len(missing_ts) != expected:
                errors.append(
                    f"ERROR: {symbol} {timeframe}: gap missing_bars mismatch "
                    f"(report={expected}, computed={len(missing_ts)})"
                )
            if df["ts"].isin(missing_ts).any():
                errors.append(
                    f"ERROR: {symbol} {timeframe}: gap range contains existing timestamps"
                )

        verified_count += 1

    if errors:
        for err in errors:
            print(err)
        print(f"ERROR: Verification failed with {len(errors)} error(s)")
    else:
        print(f"OK: verified {verified_count} entries")


if __name__ == "__main__":
    verify_outputs()
