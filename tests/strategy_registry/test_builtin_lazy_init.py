from __future__ import annotations

from strategy_registry import get_strategy


def test_get_strategy_lazy_initializes_builtins() -> None:
    strategy = get_strategy("TREND_FOLLOW_V1@1.0.0")
    assert strategy.spec.name == "TREND_FOLLOW_V1"
