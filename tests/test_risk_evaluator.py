"""Unit tests for risk evaluator outputs."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from risk.evaluator import evaluate_risk_report
from risk.contracts import RiskConfig, RiskContext


def _make_ohlcv(rows: int) -> pd.DataFrame:
    timestamps = pd.date_range("2023-01-01", periods=rows, freq="h", tz="UTC")
    close = pd.Series([100.0] * rows)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
        }
    )


def test_evaluator_green_report() -> None:
    rows = 40
    ohlcv = _make_ohlcv(rows)
    features = pd.DataFrame({"atr_14": [0.5] * rows})

    report = evaluate_risk_report(
        features,
        ohlcv,
        context=RiskContext(workspace="demo", symbol="BTC/USDT", timeframe="1h"),
    )

    assert report["risk_state"] == "GREEN"
    assert report["permission"] == "ALLOW"
    assert report["recommended_scale"] == 1.0
    assert report["metrics"]["atr_pct"] is not None
    assert report["metrics"]["realized_vol"] is not None
    assert report["metrics"]["thresholds"]["yellow_atr_pct"] > 0
    assert report["start_ts"] is not None
    assert report["end_ts"] is not None


def test_evaluator_invalid_timestamps_red() -> None:
    rows = 30
    ohlcv = _make_ohlcv(rows)
    ohlcv.loc[5, "timestamp"] = ohlcv.loc[0, "timestamp"]
    features = pd.DataFrame({"atr_14": [0.5] * rows})

    report = evaluate_risk_report(features, ohlcv)

    assert report["risk_state"] == "RED"
    assert "invalid_timestamps" in report["reasons"]


def test_evaluator_missing_values_red() -> None:
    rows = 40
    ohlcv = _make_ohlcv(rows)
    atr_values = [0.5] * rows
    for idx in range(rows - 10, rows - 7):
        atr_values[idx] = float("nan")
    features = pd.DataFrame({"atr_14": atr_values})

    config = RiskConfig(missing_lookback=10, max_missing_fraction=0.2)
    report = evaluate_risk_report(features, ohlcv, config=config)

    assert report["risk_state"] == "RED"
    assert "missing_fraction_exceeded" in report["reasons"]


def test_evaluator_invalid_index_red() -> None:
    rows = 5
    ohlcv = pd.DataFrame(
        {
            "open": [1.0] * rows,
            "high": [1.0] * rows,
            "low": [1.0] * rows,
            "close": [1.0] * rows,
        }
    )
    features = pd.DataFrame({"atr_14": [0.1] * rows})
    report = evaluate_risk_report(features, ohlcv)
    assert report["risk_state"] == "RED"
    assert "invalid_index" in report["reasons"]


def test_evaluator_invalid_close_red() -> None:
    rows = 5
    ohlcv = _make_ohlcv(rows)
    ohlcv.loc[0, "close"] = 0.0
    features = pd.DataFrame({"atr_14": [0.1] * rows})
    report = evaluate_risk_report(features, ohlcv)
    assert report["risk_state"] == "RED"
    assert "invalid_close" in report["reasons"]


def test_evaluator_missing_metrics_red() -> None:
    rows = 30
    ohlcv = _make_ohlcv(rows)
    features = pd.DataFrame({"atr_14": [float("nan")] * rows})
    report = evaluate_risk_report(features, ohlcv)
    assert report["risk_state"] == "RED"
    assert "missing_metrics" in report["reasons"]


def test_evaluator_missing_metrics_close_nan() -> None:
    rows = 30
    ohlcv = _make_ohlcv(rows)
    ohlcv.loc[rows - 1, "close"] = float("nan")
    features = pd.DataFrame({"atr_14": [0.1] * rows})
    report = evaluate_risk_report(features, ohlcv)
    assert report["risk_state"] == "RED"
    assert "missing_metrics" in report["reasons"]


def test_evaluator_determinism() -> None:
    rows = 40
    ohlcv = _make_ohlcv(rows)
    features = pd.DataFrame({"atr_14": [0.5] * rows})
    report_a = evaluate_risk_report(features, ohlcv)
    report_b = evaluate_risk_report(features, ohlcv)
    assert report_a == report_b


def test_evaluator_output_fields() -> None:
    rows = 40
    ohlcv = _make_ohlcv(rows)
    features = pd.DataFrame({"atr_14": [0.5] * rows})
    report = evaluate_risk_report(features, ohlcv)
    assert report["metrics"]["atr_pct"] is not None
    assert report["metrics"]["realized_vol"] is not None
    assert isinstance(report["metrics"]["thresholds"], dict)
    assert isinstance(report["thresholds"], dict)
    assert report["evaluated_at"] is not None
    parsed = pd.to_datetime(report["evaluated_at"], utc=True, errors="coerce")
    assert not pd.isna(parsed)


def test_evaluator_non_monotonic_timestamps_red() -> None:
    rows = 10
    ohlcv = _make_ohlcv(rows)
    ohlcv.loc[5, "timestamp"] = ohlcv.loc[2, "timestamp"] - pd.Timedelta(hours=1)
    features = pd.DataFrame({"atr_14": [0.1] * rows})
    report = evaluate_risk_report(features, ohlcv)
    assert report["risk_state"] == "RED"
    assert "invalid_timestamps" in report["reasons"]


def test_evaluator_realized_vol_computation() -> None:
    close = pd.Series([100.0, 101.0, 102.0, 103.0])
    ohlcv = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=4, freq="h", tz="UTC"),
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
        }
    )
    features = pd.DataFrame({"atr_14": [0.5] * 4})
    config = RiskConfig(realized_vol_window=3)
    report = evaluate_risk_report(features, ohlcv, config=config)
    log_returns = np.log(close).diff()
    realized = log_returns.rolling(window=3, min_periods=3).std(ddof=0)
    expected = float(realized.iloc[-1])
    assert report["metrics"]["realized_vol"] == pytest.approx(expected)
