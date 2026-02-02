"""Deterministic 1m OHLCV data quality report for workspace artifacts.

Schema (workspace/data_quality.json):
{
  "schema_version": 1,
  "generated_at_utc": "2026-01-01T00:00:00Z",
  "symbol": "BTC/USDT",
  "timeframe": "1m",
  "expected_interval_seconds": 60,
  "start_ts": "2026-01-01T00:00:00Z",
  "end_ts": "2026-01-01T00:59:00Z",
  "overall_status": "PASS|WARN|FAIL",
  "summary": {
    "counts_by_severity": {"PASS": 4, "WARN": 0, "FAIL": 0},
    "counts_by_check": {"gaps": 0, "duplicates": 0, "out_of_order": 0, "zero_volume": 0}
  },
  "findings": [
    {
      "check_id": "gaps|duplicates|out_of_order|zero_volume",
      "severity": "WARN|FAIL",
      "start_ts": "2026-01-01T00:10:00Z",
      "end_ts": "2026-01-01T00:12:00Z",
      "code": "missing_timestamp|duplicate_timestamp|out_of_order|zero_volume"
    }
  ]
}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _format_ts(ts: pd.Timestamp) -> str:
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    ts = ts.tz_convert("UTC")
    return ts.isoformat().replace("+00:00", "Z")


def _find_missing_ranges(
    expected: pd.DatetimeIndex, actual_set: set[pd.Timestamp]
) -> list[tuple[str, str]]:
    missing = [ts for ts in expected if ts not in actual_set]
    if not missing:
        return []

    missing = sorted(missing)
    ranges: list[tuple[str, str]] = []
    start = missing[0]
    prev = missing[0]
    for ts in missing[1:]:
        if ts - prev != pd.Timedelta(minutes=1):
            ranges.append((_format_ts(start), _format_ts(prev)))
            start = ts
        prev = ts
    ranges.append((_format_ts(start), _format_ts(prev)))
    return ranges


def build_quality_report(df: pd.DataFrame, symbol: str, timeframe: str) -> dict[str, Any]:
    if timeframe != "1m":
        raise ValueError("timeframe_must_be_1m")
    if "ts" not in df.columns:
        raise ValueError("missing_ts")

    if df.empty:
        start_ts = ""
        end_ts = ""
        generated_at_utc = ""
        expected = pd.DatetimeIndex([], tz="UTC")
        actual_set: set[pd.Timestamp] = set()
    else:
        ts_series = pd.to_datetime(df["ts"], utc=True)
        start_ts = _format_ts(ts_series.min())
        end_ts = _format_ts(ts_series.max())
        generated_at_utc = end_ts
        expected = pd.date_range(ts_series.min(), ts_series.max(), freq="1min", tz="UTC")
        actual_set = set(ts_series)

    out_of_order = bool(not df["ts"].is_monotonic_increasing) if not df.empty else False
    duplicates_series = (
        pd.to_datetime(df["ts"], utc=True).duplicated() if not df.empty else pd.Series([])
    )
    duplicate_ts = (
        sorted(set(pd.to_datetime(df.loc[duplicates_series, "ts"], utc=True)))
        if not df.empty
        else []
    )
    zero_volume_ts = (
        sorted(set(pd.to_datetime(df.loc[df["volume"] == 0, "ts"], utc=True)))
        if not df.empty and "volume" in df.columns
        else []
    )

    gap_ranges = _find_missing_ranges(expected, actual_set)

    counts_by_check = {
        "gaps": int(
            sum(
                (pd.Timestamp(end) - pd.Timestamp(start)).total_seconds() / 60 + 1
                for start, end in gap_ranges
            )
        )
        if gap_ranges
        else 0,
        "duplicates": len(duplicate_ts),
        "out_of_order": 1 if out_of_order else 0,
        "zero_volume": len(zero_volume_ts),
    }

    check_severity = {
        "gaps": "FAIL" if counts_by_check["gaps"] > 0 else "PASS",
        "duplicates": "FAIL" if counts_by_check["duplicates"] > 0 else "PASS",
        "out_of_order": "FAIL" if counts_by_check["out_of_order"] > 0 else "PASS",
        "zero_volume": "WARN" if counts_by_check["zero_volume"] > 0 else "PASS",
    }

    counts_by_severity = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for sev in check_severity.values():
        counts_by_severity[sev] += 1

    findings: list[dict[str, str]] = []
    for start, end in gap_ranges:
        findings.append(
            {
                "check_id": "gaps",
                "severity": "FAIL",
                "start_ts": start,
                "end_ts": end,
                "code": "missing_timestamp",
            }
        )
    for ts in duplicate_ts:
        formatted = _format_ts(ts)
        findings.append(
            {
                "check_id": "duplicates",
                "severity": "FAIL",
                "start_ts": formatted,
                "end_ts": formatted,
                "code": "duplicate_timestamp",
            }
        )
    if out_of_order:
        findings.append(
            {
                "check_id": "out_of_order",
                "severity": "FAIL",
                "start_ts": "",
                "end_ts": "",
                "code": "out_of_order",
            }
        )
    for ts in zero_volume_ts:
        formatted = _format_ts(ts)
        findings.append(
            {
                "check_id": "zero_volume",
                "severity": "WARN",
                "start_ts": formatted,
                "end_ts": formatted,
                "code": "zero_volume",
            }
        )

    findings = sorted(
        findings,
        key=lambda item: (item["check_id"], item["start_ts"], item["end_ts"], item["code"]),
    )

    overall_status = (
        "FAIL"
        if counts_by_severity["FAIL"] > 0
        else ("WARN" if counts_by_severity["WARN"] > 0 else "PASS")
    )

    return {
        "schema_version": 1,
        "generated_at_utc": generated_at_utc,
        "symbol": symbol,
        "timeframe": timeframe,
        "expected_interval_seconds": 60,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "overall_status": overall_status,
        "summary": {
            "counts_by_severity": counts_by_severity,
            "counts_by_check": counts_by_check,
        },
        "findings": findings,
    }


def serialize_quality_report(report: dict[str, Any]) -> bytes:
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return (payload + "\n").encode("utf-8")


def write_quality_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialize_quality_report(report))
