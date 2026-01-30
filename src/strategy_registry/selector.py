from __future__ import annotations

from typing import Iterable

from .registry import StrategySpec, get_strategy


def select_strategy(menu_choice: str, registry: Iterable[StrategySpec] | None = None) -> StrategySpec:
    if registry is None:
        return get_strategy(menu_choice)
    candidates = [spec for spec in registry if spec.name == menu_choice]
    if not candidates:
        raise ValueError("strategy_not_found")
    if len(candidates) > 1:
        raise ValueError("strategy_name_ambiguous")
    return candidates[0]
