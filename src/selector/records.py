from __future__ import annotations

from selector.types import SelectionResult


def selection_to_record(selection: SelectionResult) -> dict[str, object]:
    return {
        "strategy_id": selection.strategy_id,
        "rule_id": selection.rule_id,
        "reason": selection.reason,
        "inputs": selection.inputs,
    }


__all__ = ["selection_to_record"]
