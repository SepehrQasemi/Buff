from __future__ import annotations

from risk.types import RiskState
from selector.types import MarketSignals, SelectionResult
from strategies.menu import STRATEGY_MENU


def _ensure_strategy_id(strategy_id: str) -> None:
    if strategy_id not in STRATEGY_MENU:
        raise ValueError(f"Unknown strategy_id: {strategy_id}")


def _result(
    *,
    strategy_id: str | None,
    reason: str,
    rule_id: str,
    inputs: dict[str, object],
) -> SelectionResult:
    if strategy_id is not None:
        _ensure_strategy_id(strategy_id)
    return SelectionResult(
        strategy_id=strategy_id,
        reason=reason,
        rule_id=rule_id,
        inputs=inputs,
    )


def select_strategy(signals: MarketSignals, risk_state: RiskState) -> SelectionResult:
    trend_state = signals.get("trend_state", "unknown")
    volatility_regime = signals.get("volatility_regime", "unknown")
    structure_state = signals.get("structure_state", "unknown")
    risk_state_value = risk_state.value

    # Risk precedence: RED/YELLOW override any market-derived rules.
    if risk_state == RiskState.RED:
        return _result(
            strategy_id=None,
            reason="risk=RED",
            rule_id="R0",
            inputs={"risk_state": risk_state_value},
        )

    if risk_state == RiskState.YELLOW:
        return _result(
            strategy_id="DEFENSIVE",
            reason="risk=YELLOW",
            rule_id="R1",
            inputs={"risk_state": risk_state_value},
        )

    if (
        trend_state in {"up", "down"}
        and volatility_regime in {"low", "mid"}
        and structure_state == "breakout"
    ):
        return _result(
            strategy_id="TREND_FOLLOW",
            reason="trend+breakout & vol not high",
            rule_id="R2",
            inputs={
                "risk_state": risk_state_value,
                "trend_state": trend_state,
                "volatility_regime": volatility_regime,
                "structure_state": structure_state,
            },
        )

    if (
        trend_state == "flat"
        and volatility_regime in {"low", "mid"}
        and structure_state == "meanrevert"
    ):
        return _result(
            strategy_id="MEAN_REVERT",
            reason="range+meanrevert & vol not high",
            rule_id="R3",
            inputs={
                "risk_state": risk_state_value,
                "trend_state": trend_state,
                "volatility_regime": volatility_regime,
                "structure_state": structure_state,
            },
        )

    return _result(
        strategy_id=None,
        reason="no_rule_matched",
        rule_id="R9",
        inputs={"risk_state": risk_state_value},
    )
