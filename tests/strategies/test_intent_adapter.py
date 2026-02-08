from __future__ import annotations

from strategy_registry import list_intent_strategies
from strategies.registry import list_strategies


def test_intent_adapter_matches_builtin_registry() -> None:
    intent = list_intent_strategies()
    builtins = list_strategies()
    assert len(intent) == 20
    assert [item["id"] for item in intent] == [item["id"] for item in builtins]
