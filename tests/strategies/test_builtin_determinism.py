from __future__ import annotations

from strategies.registry import get_strategy, list_strategies

from tests.strategies.helpers import run_intents, synthetic_ohlcv


def test_builtin_strategies_deterministic() -> None:
    ohlcv = synthetic_ohlcv(80)
    first_run: dict[str, list[str]] = {}
    for schema in list_strategies():
        strategy = get_strategy(f"{schema['id']}@{schema['version']}")
        first_run[schema["id"]] = run_intents(strategy, ohlcv)

    for schema in list_strategies():
        strategy = get_strategy(f"{schema['id']}@{schema['version']}")
        second = run_intents(strategy, ohlcv)
        assert second == first_run[schema["id"]]
