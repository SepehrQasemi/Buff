from __future__ import annotations

from pathlib import Path

from features.build_features import build_features
from features.regime import build_market_state
from tests.fixtures.ohlcv_factory import make_ohlcv

FORBIDDEN_TERMS = [
    "signal",
    "side",
    "position",
    "long",
    "short",
    "entry",
    "exit",
    "buy",
    "sell",
    "strategy_id",
]

REQUIRED_COLUMNS = [
    "log_return_1",
    "log_return_5",
    "log_return_20",
    "volume_zscore_20",
    "ema_20",
    "ema_50",
    "ema_spread_20_50_pct",
    "rsi_14",
    "rsi_slope_14_5",
    "atr_14",
    "atr_pct",
    "realized_vol_20",
    "adx_14",
    "trend_state",
    "momentum_state",
    "volatility_regime",
]


def _scan_feature_sources() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    feature_dir = repo_root / "src" / "features"
    for path in sorted(feature_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for term in FORBIDDEN_TERMS:
            assert term not in text, f"Forbidden term '{term}' found in {path}"


def test_no_trading_terms_in_outputs_or_sources() -> None:
    df = make_ohlcv(200)
    market_state = build_market_state(build_features(df))

    columns_lower = [col.lower() for col in market_state.columns]
    for term in FORBIDDEN_TERMS:
        assert all(term not in col for col in columns_lower), f"Forbidden term '{term}' in columns"

    _scan_feature_sources()


def test_feature_invariants() -> None:
    df = make_ohlcv(240)
    market_state = build_market_state(build_features(df))

    assert market_state.index.is_monotonic_increasing
    assert not market_state.index.has_duplicates

    for col in REQUIRED_COLUMNS:
        assert col in market_state.columns

    allowed_trend = {"down", "flat", "up"}
    allowed_momentum = {"bear", "neutral", "bull"}
    allowed_volatility = {"low", "normal", "high"}

    trend_vals = set(market_state["trend_state"].dropna().unique())
    momentum_vals = set(market_state["momentum_state"].dropna().unique())
    volatility_vals = set(market_state["volatility_regime"].dropna().unique())

    assert trend_vals <= allowed_trend
    assert momentum_vals <= allowed_momentum
    assert volatility_vals <= allowed_volatility
