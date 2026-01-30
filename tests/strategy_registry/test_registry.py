from __future__ import annotations

import pytest

from strategy_registry.registry import StrategySpec, _reset_registry, register_strategy, list_strategies
from strategy_registry.selector import select_strategy


def test_registry_deterministic_order() -> None:
    _reset_registry()
    register_strategy(
        StrategySpec(
            name="beta",
            version="1.0.0",
            description="beta",
            required_features=["a"],
        )
    )
    register_strategy(
        StrategySpec(
            name="alpha",
            version="1.0.0",
            description="alpha",
            required_features=["b"],
        )
    )
    names = [spec.name for spec in list_strategies()]
    assert names == ["alpha", "beta"]


def test_select_unknown_strategy() -> None:
    with pytest.raises(ValueError):
        select_strategy("missing", registry=[])
