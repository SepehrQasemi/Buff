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

MEAN_REVERT_V1 = StrategySpecImpl(
    strategy_id="MEAN_REVERT_V1",
    name="Mean Revert V1",
    description="Bollinger/RSI mean reversion profile.",
    allowed_risk_states={RiskState.GREEN},
    tags={"range", "v1"},
)

DEFENSIVE = StrategySpecImpl(
    strategy_id="DEFENSIVE",
    name="Defensive",
    description="Defensive posture for elevated risk or uncertain conditions.",
    allowed_risk_states={RiskState.GREEN, RiskState.YELLOW},
    tags={"defensive", "meta"},
)

TREND_FOLLOW_V1 = StrategySpecImpl(
    strategy_id="TREND_FOLLOW_V1",
    name="Trend Follow V1",
    description="EMA20/EMA50 trend-following with RSI confirmation.",
    allowed_risk_states={RiskState.GREEN},
    tags={"trend", "v1"},
)


STRATEGY_MENU: dict[str, StrategySpec] = {
    TREND_FOLLOW.strategy_id: TREND_FOLLOW,
    MEAN_REVERT.strategy_id: MEAN_REVERT,
    DEFENSIVE.strategy_id: DEFENSIVE,
    TREND_FOLLOW_V1.strategy_id: TREND_FOLLOW_V1,
    MEAN_REVERT_V1.strategy_id: MEAN_REVERT_V1,
}


def list_strategies() -> list[StrategySpec]:
    return list(STRATEGY_MENU.values())
