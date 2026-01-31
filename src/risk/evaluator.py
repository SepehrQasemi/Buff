"""Risk policy evaluator and report builder."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from risk.policy import evaluate_policy
from risk.types import RiskConfig, RiskContext, RiskInputs, threshold_snapshot


def _to_datetime_index(df: pd.DataFrame) -> pd.DatetimeIndex | None:
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index
    if "timestamp" in df.columns:
        return pd.DatetimeIndex(pd.to_datetime(df["timestamp"], errors="coerce", utc=True))
    if "ts" in df.columns:
        return pd.DatetimeIndex(pd.to_datetime(df["ts"], errors="coerce", utc=True))
    return None


def _timestamps_valid(index: pd.DatetimeIndex | None) -> bool:
    if index is None or index.isna().any():
        return False
    if index.duplicated().any():
        return False
    return bool(index.is_monotonic_increasing)


def _compute_realized_vol(close: pd.Series, window: int) -> pd.Series:
    close = close.astype(float)
    close = close.mask(close <= 0)
    log_returns = np.log(close).diff()
    return log_returns.rolling(window=window, min_periods=window).std(ddof=0)


def _missing_fraction(series_list: list[pd.Series], lookback: int) -> float:
    if not series_list:
        return 1.0
    frame = pd.concat(series_list, axis=1)
    if lookback > 0:
        frame = frame.tail(lookback)
    if frame.empty:
        return 1.0
    missing = frame.isna().any(axis=1)
    return float(missing.mean())


def evaluate_risk_report(
    features: pd.DataFrame,
    ohlcv: pd.DataFrame,
    *,
    config: RiskConfig | None = None,
    context: RiskContext | None = None,
) -> dict[str, Any]:
    """Evaluate the risk policy using features and OHLCV data."""

    if config is None:
        config = RiskConfig()
    if context is None:
        context = RiskContext()

    timestamps = _to_datetime_index(ohlcv)
    invalid_index = timestamps is None
    timestamps_valid = _timestamps_valid(timestamps)

    close = ohlcv["close"].astype(float) if "close" in ohlcv.columns else None
    invalid_close = close is None
    if close is not None:
        invalid_close = bool((close <= 0).any())
    atr = features[config.atr_feature] if config.atr_feature in features.columns else None

    atr_pct_series = None
    if atr is not None and close is not None:
        if not atr.index.equals(close.index):
            if len(atr) == len(close):
                atr = atr.reset_index(drop=True)
                close = close.reset_index(drop=True)
            else:
                close = close.reindex(atr.index)
        atr_pct_series = atr.astype(float) / close

    realized_vol_series = None
    if close is not None:
        realized_vol_series = _compute_realized_vol(close, config.realized_vol_window)

    series_list = [s for s in [atr_pct_series, realized_vol_series] if s is not None]
    missing_fraction = _missing_fraction(series_list, config.missing_lookback)

    latest_atr_pct = float(atr_pct_series.iloc[-1]) if atr_pct_series is not None else None
    latest_vol = float(realized_vol_series.iloc[-1]) if realized_vol_series is not None else None

    latest_metrics_valid = True
    for value in (latest_atr_pct, latest_vol):
        if value is None or np.isnan(value):
            latest_metrics_valid = False
            break

    decision = evaluate_policy(
        RiskInputs(
            atr_pct=latest_atr_pct,
            realized_vol=latest_vol,
            missing_fraction=missing_fraction,
            timestamps_valid=timestamps_valid,
            latest_metrics_valid=latest_metrics_valid,
            invalid_index=invalid_index,
            invalid_close=invalid_close,
        ),
        config,
    )

    start_ts = None
    end_ts = None
    as_of = None
    if timestamps is not None and len(timestamps) > 0:
        start_ts = pd.Timestamp(timestamps.min()).isoformat()
        end_ts = pd.Timestamp(timestamps.max()).isoformat()
        as_of = end_ts

    thresholds = dict(threshold_snapshot(config))
    report: dict[str, Any] = {
        "risk_report_version": 1,
        "run_id": context.run_id,
        "workspace": context.workspace,
        "symbol": context.symbol,
        "timeframe": context.timeframe,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "evaluated_at": as_of,
        "risk_state": decision.state.value,
        "permission": decision.permission.value,
        "recommended_scale": decision.recommended_scale,
        "reasons": list(decision.reasons),
        "thresholds": thresholds,
        "metrics": {
            "atr_pct": latest_atr_pct,
            "realized_vol": latest_vol,
            "missing_fraction": missing_fraction,
            "as_of": as_of,
            "thresholds": thresholds,
        },
        "config": asdict(config),
    }

    return report
