from __future__ import annotations

from strategies.registry import StrategyRegistry


def select_strategy(strategy_id: str, registry: StrategyRegistry) -> str:
    if not registry.is_registered(strategy_id):
        raise ValueError("strategy_not_registered")
    return strategy_id
