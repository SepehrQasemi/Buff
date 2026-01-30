from __future__ import annotations

from risk.types import RiskState
from strategies.base import StrategySpec, StrategySpecImpl


TREND_FOLLOW = StrategySpecImpl(
    strategy_id="TREND_FOLLOW",
    name="Trend Follow",
    description="Trend-following profile for breakout conditions in stable volatility.",
    allowed_risk_states={RiskState.GREEN},
    tags={"trend"},
)

MEAN_REVERT = StrategySpecImpl(
    strategy_id="MEAN_REVERT",
    name="Mean Revert",
    description="Range-bound mean reversion profile for stable volatility.",
    allowed_risk_states={RiskState.GREEN},
    tags={"range"},
)

DEFENSIVE = StrategySpecImpl(
    strategy_id="DEFENSIVE",
    name="Defensive",
    description="Defensive posture for elevated risk or uncertain conditions.",
    allowed_risk_states={RiskState.GREEN, RiskState.YELLOW},
    tags={"defensive", "meta"},
)


STRATEGY_MENU: dict[str, StrategySpec] = {
    TREND_FOLLOW.strategy_id: TREND_FOLLOW,
    MEAN_REVERT.strategy_id: MEAN_REVERT,
    DEFENSIVE.strategy_id: DEFENSIVE,
}


def list_strategies() -> list[StrategySpec]:
    return list(STRATEGY_MENU.values())
