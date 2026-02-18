from __future__ import annotations

from risk.contracts import RiskState
from selector.selector import select_strategy


def _signals(
    *,
    trend_state: str = "unknown",
    volatility_regime: str = "unknown",
    momentum_state: str = "unknown",
    structure_state: str = "unknown",
) -> dict:
    return {
        "trend_state": trend_state,
        "volatility_regime": volatility_regime,
        "momentum_state": momentum_state,
        "structure_state": structure_state,
    }


def test_red_no_trade() -> None:
    result = select_strategy(_signals(), RiskState.RED)
    assert result.strategy_id is None
    assert result.rule_id == "R0"
    assert result.reason == "risk=RED"


def test_yellow_defensive() -> None:
    result = select_strategy(_signals(), RiskState.YELLOW)
    assert result.strategy_id == "DEFENSIVE"
    assert result.rule_id == "R1"
    assert result.reason == "risk=YELLOW"


def test_breakout_trend_low_vol() -> None:
    result = select_strategy(
        _signals(trend_state="up", volatility_regime="low", structure_state="breakout"),
        RiskState.GREEN,
    )
    assert result.strategy_id == "TREND_FOLLOW"
    assert result.rule_id == "R2"
    assert result.reason == "trend+breakout & vol not high"


def test_flat_meanrevert_mid_vol() -> None:
    result = select_strategy(
        _signals(trend_state="flat", volatility_regime="mid", structure_state="meanrevert"),
        RiskState.GREEN,
    )
    assert result.strategy_id == "MEAN_REVERT"
    assert result.rule_id == "R3"
    assert result.reason == "range+meanrevert & vol not high"


def test_unknowns_default_no_trade() -> None:
    result = select_strategy(_signals(), RiskState.GREEN)
    assert result.strategy_id is None
    assert result.rule_id == "R9"
    assert result.reason == "no_rule_matched"


def test_inputs_snapshot_contains_only_used_keys() -> None:
    result = select_strategy(_signals(), RiskState.YELLOW)
    assert result.inputs == {"risk_state": "YELLOW"}


def test_risk_precedence_yellow_over_market_rules() -> None:
    result = select_strategy(
        _signals(trend_state="up", volatility_regime="low", structure_state="breakout"),
        RiskState.YELLOW,
    )
    assert result.strategy_id == "DEFENSIVE"
    assert result.rule_id == "R1"


def test_risk_precedence_red_over_market_rules() -> None:
    result = select_strategy(
        _signals(trend_state="flat", volatility_regime="mid", structure_state="meanrevert"),
        RiskState.RED,
    )
    assert result.strategy_id is None
    assert result.rule_id == "R0"
