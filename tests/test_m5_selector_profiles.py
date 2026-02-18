from __future__ import annotations

from risk.contracts import RiskState
from selector.selector import select_strategy


def test_red_veto() -> None:
    signals = {
        "trend_state": "unknown",
        "volatility_regime": "unknown",
        "momentum_state": "unknown",
        "structure_state": "unknown",
    }
    result = select_strategy(signals, RiskState.RED)
    assert result.strategy_id is None
    assert result.rule_id == "R0"


def test_green_select_trend_conservative_up() -> None:
    signals = {
        "trend_state": "up",
        "volatility_regime": "low",
        "momentum_state": "neutral",
        "structure_state": "breakout",
    }
    result = select_strategy(signals, RiskState.GREEN)
    assert result.strategy_id == "TREND_FOLLOW"
    assert result.rule_id == "R2"


def test_yellow_only_conservative() -> None:
    signals = {
        "trend_state": "down",
        "volatility_regime": "mid",
        "momentum_state": "bear",
        "structure_state": "breakout",
    }
    result = select_strategy(signals, RiskState.YELLOW)
    assert result.strategy_id == "DEFENSIVE"
    assert result.rule_id == "R1"


def test_missing_keys_returns_none() -> None:
    result = select_strategy({}, RiskState.GREEN)
    assert result.strategy_id is None
    assert result.rule_id == "R9"


def test_deterministic_repeatability() -> None:
    signals = {
        "trend_state": "flat",
        "volatility_regime": "low",
        "momentum_state": "neutral",
        "structure_state": "meanrevert",
    }
    result_a = select_strategy(signals, RiskState.GREEN)
    result_b = select_strategy(signals, RiskState.GREEN)
    assert result_a == result_b
