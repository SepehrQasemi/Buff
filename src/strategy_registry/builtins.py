from __future__ import annotations

from typing import Any

from strategy_registry.registry import StrategyDefinition, StrategyRegistryError, register_strategy
from strategies.runners.mean_revert_v1 import MEAN_REVERT_V1_SPEC, mean_revert_v1_runner
from strategies.runners.trend_follow_v1 import TREND_FOLLOW_V1_SPEC, trend_follow_v1_runner

BUILTIN_STRATEGY_IDS = {
    f"{TREND_FOLLOW_V1_SPEC.name}@{TREND_FOLLOW_V1_SPEC.version}",
    f"{MEAN_REVERT_V1_SPEC.name}@{MEAN_REVERT_V1_SPEC.version}",
}


def register_builtin_strategies() -> None:
    for spec, runner in (
        (TREND_FOLLOW_V1_SPEC, trend_follow_v1_runner),
        (MEAN_REVERT_V1_SPEC, mean_revert_v1_runner),
    ):
        try:
            register_strategy(StrategyDefinition(spec=spec, runner=runner))
        except StrategyRegistryError as exc:
            if exc.code != "strategy_already_registered":
                raise


def list_intent_strategies() -> list[dict[str, Any]]:
    from strategies.registry import list_strategies as list_intent_strategies

    return list_intent_strategies()


__all__ = ["register_builtin_strategies", "BUILTIN_STRATEGY_IDS", "list_intent_strategies"]
