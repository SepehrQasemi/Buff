"""Explicit classification examples for each regime."""

from __future__ import annotations

from pathlib import Path

from buff.regimes.evaluator import evaluate_regime
from buff.regimes.parser import load_regime_config


def _base_features() -> dict[str, float]:
    return {
        "adx_14": 22.0,
        "atr_pct": 0.015,
        "realized_vol_20": 0.02,
        "rsi_14": 50.0,
        "rsi_slope_14_5": 0.0,
        "ema_spread_20_50": 0.0,
        "vwap_typical_daily": 100.0,
        "bb_upper_20_2": 101.0,
        "bb_lower_20_2": 99.0,
    }


def test_regime_examples() -> None:
    config = load_regime_config(Path("knowledge/regimes.yaml"))

    risk_off = _base_features()
    risk_off.update({"atr_pct": 0.04})
    assert evaluate_regime(risk_off, config).regime_id == "RISK_OFF"

    high_vol_trend = _base_features()
    high_vol_trend.update({"adx_14": 30.0, "atr_pct": 0.021})
    assert evaluate_regime(high_vol_trend, config).regime_id == "HIGH_VOL_TREND"

    low_vol_trend = _base_features()
    low_vol_trend.update({"adx_14": 30.0, "atr_pct": 0.008, "realized_vol_20": 0.012})
    assert evaluate_regime(low_vol_trend, config).regime_id == "LOW_VOL_TREND"

    high_vol_range = _base_features()
    high_vol_range.update({"adx_14": 15.0, "atr_pct": 0.021})
    assert evaluate_regime(high_vol_range, config).regime_id == "HIGH_VOL_RANGE"

    low_vol_range = _base_features()
    low_vol_range.update({"adx_14": 15.0, "atr_pct": 0.008, "realized_vol_20": 0.012})
    assert evaluate_regime(low_vol_range, config).regime_id == "LOW_VOL_RANGE"

    mean_reversion = _base_features()
    mean_reversion.update(
        {
            "adx_14": 15.0,
            "atr_pct": 0.012,
            "realized_vol_20": 0.015,
            "rsi_14": 75.0,
            "rsi_slope_14_5": 0.5,
            "ema_spread_20_50": 0.2,
        }
    )
    assert evaluate_regime(mean_reversion, config).regime_id == "MEAN_REVERSION_BIAS"

    neutral = _base_features()
    assert evaluate_regime(neutral, config).regime_id == "NEUTRAL"
