from __future__ import annotations

import pandas as pd

from buff.data.quality_report import build_quality_report, serialize_quality_report


def _frame(ts: list[str], volume: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": pd.to_datetime(ts, utc=True),
            "open": [100.0] * len(ts),
            "high": [101.0] * len(ts),
            "low": [99.0] * len(ts),
            "close": [100.0] * len(ts),
            "volume": volume,
        }
    )


def test_detects_gaps() -> None:
    df = _frame(
        ["2023-01-01T00:00:00Z", "2023-01-01T00:02:00Z"],
        [1.0, 1.0],
    )
    report = build_quality_report(df, "BTC/USDT", "1m")
    findings = [f for f in report["findings"] if f["check_id"] == "gaps"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "FAIL"
    assert report["summary"]["counts_by_check"]["gaps"] == 1
    assert report["summary"]["counts_by_severity"]["FAIL"] == 1


def test_detects_duplicates() -> None:
    df = _frame(
        ["2023-01-01T00:00:00Z", "2023-01-01T00:00:00Z", "2023-01-01T00:01:00Z"],
        [1.0, 1.0, 1.0],
    )
    report = build_quality_report(df, "BTC/USDT", "1m")
    findings = [f for f in report["findings"] if f["check_id"] == "duplicates"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "FAIL"
    assert report["summary"]["counts_by_check"]["duplicates"] == 1
    assert report["summary"]["counts_by_severity"]["FAIL"] == 1


def test_detects_out_of_order() -> None:
    df = _frame(
        ["2023-01-01T00:01:00Z", "2023-01-01T00:00:00Z"],
        [1.0, 1.0],
    )
    report = build_quality_report(df, "BTC/USDT", "1m")
    findings = [f for f in report["findings"] if f["check_id"] == "out_of_order"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "FAIL"
    assert report["summary"]["counts_by_check"]["out_of_order"] == 1
    assert report["summary"]["counts_by_severity"]["FAIL"] == 1


def test_detects_zero_volume() -> None:
    df = _frame(
        ["2023-01-01T00:00:00Z", "2023-01-01T00:01:00Z"],
        [0.0, 1.0],
    )
    report = build_quality_report(df, "BTC/USDT", "1m")
    findings = [f for f in report["findings"] if f["check_id"] == "zero_volume"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "WARN"
    assert report["summary"]["counts_by_check"]["zero_volume"] == 1
    assert report["summary"]["counts_by_severity"]["WARN"] == 1
    assert report["overall_status"] == "WARN"


def test_quality_report_deterministic_bytes() -> None:
    df = _frame(
        ["2023-01-01T00:00:00Z", "2023-01-01T00:02:00Z"],
        [1.0, 1.0],
    )
    report_a = build_quality_report(df, "BTC/USDT", "1m")
    report_b = build_quality_report(df, "BTC/USDT", "1m")
    assert serialize_quality_report(report_a) == serialize_quality_report(report_b)


def test_findings_order_is_stable() -> None:
    df = _frame(
        [
            "2023-01-01T00:01:00Z",
            "2023-01-01T00:00:00Z",
            "2023-01-01T00:00:00Z",
            "2023-01-01T00:03:00Z",
        ],
        [1.0, 0.0, 2.0, 1.0],
    )
    report = build_quality_report(df, "BTC/USDT", "1m")
    order = [(f["check_id"], f["start_ts"]) for f in report["findings"]]
    assert order == [
        ("duplicates", "2023-01-01T00:00:00Z"),
        ("gaps", "2023-01-01T00:02:00Z"),
        ("out_of_order", ""),
        ("zero_volume", "2023-01-01T00:00:00Z"),
    ]
