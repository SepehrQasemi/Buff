"""Safe rule evaluation engine for fundamental risk DSL."""

from __future__ import annotations

from typing import Any


def evaluate_when(when: dict[str, Any], inputs: dict[str, Any]) -> tuple[bool, str]:
    if "all" in when:
        return _evaluate_all(when["all"], inputs)
    if "any" in when:
        return _evaluate_any(when["any"], inputs)
    return False, "missing_all_any"


def _evaluate_all(predicates: list[Any], inputs: dict[str, Any]) -> tuple[bool, str]:
    for predicate in predicates:
        matched, reason = _evaluate_predicate(predicate, inputs)
        if not matched:
            return False, reason
    return True, "all_conditions_matched"


def _evaluate_any(predicates: list[Any], inputs: dict[str, Any]) -> tuple[bool, str]:
    reasons: list[str] = []
    for predicate in predicates:
        matched, reason = _evaluate_predicate(predicate, inputs)
        if matched:
            return True, reason
        reasons.append(reason)
    return False, "any_conditions_failed:" + ";".join(reasons)


def _evaluate_predicate(predicate: dict[str, Any], inputs: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(predicate, dict) or len(predicate) != 1:
        return False, "invalid_predicate"
    operator, config = next(iter(predicate.items()))
    if operator == "eq":
        key, target = next(iter(config.items()))
        return _compare_eq(key, target, inputs)
    if operator == "gte":
        key, target = next(iter(config.items()))
        return _compare_gte(key, target, inputs)
    if operator == "lte":
        key, target = next(iter(config.items()))
        return _compare_lte(key, target, inputs)
    if operator == "gte_abs_diff":
        return _compare_abs_diff(config, inputs, operator, lambda diff, value: diff >= value)
    if operator == "lte_abs_diff":
        return _compare_abs_diff(config, inputs, operator, lambda diff, value: diff <= value)
    if operator == "missing":
        return _compare_missing(config, inputs)
    return False, f"unknown_operator:{operator}"


def _compare_eq(key: str, target: Any, inputs: dict[str, Any]) -> tuple[bool, str]:
    value = inputs.get(key)
    if value is None:
        return False, f"missing:{key}"
    return value == target, f"eq:{key}:{value}"


def _compare_gte(key: str, target: Any, inputs: dict[str, Any]) -> tuple[bool, str]:
    value = inputs.get(key)
    if value is None:
        return False, f"missing:{key}"
    try:
        return float(value) >= float(target), f"gte:{key}:{value}"
    except (TypeError, ValueError):
        return False, f"invalid_numeric:{key}"


def _compare_lte(key: str, target: Any, inputs: dict[str, Any]) -> tuple[bool, str]:
    value = inputs.get(key)
    if value is None:
        return False, f"missing:{key}"
    try:
        return float(value) <= float(target), f"lte:{key}:{value}"
    except (TypeError, ValueError):
        return False, f"invalid_numeric:{key}"


def _compare_abs_diff(
    config: dict[str, Any],
    inputs: dict[str, Any],
    operator: str,
    comparator,
) -> tuple[bool, str]:
    lhs_key = config.get("lhs")
    rhs_key = config.get("rhs")
    threshold = config.get("value")
    lhs = inputs.get(lhs_key)
    rhs = inputs.get(rhs_key)
    if lhs is None:
        return False, f"missing:{lhs_key}"
    if rhs is None:
        return False, f"missing:{rhs_key}"
    try:
        diff = abs(float(lhs) - float(rhs))
        return comparator(diff, float(threshold)), f"{operator}:{diff}"
    except (TypeError, ValueError):
        return False, f"invalid_numeric:{lhs_key}:{rhs_key}"


def _compare_missing(config: Any, inputs: dict[str, Any]) -> tuple[bool, str]:
    if isinstance(config, dict):
        key = config.get("value")
    else:
        key = config
    if not isinstance(key, str):
        return False, "invalid_missing_key"
    return key not in inputs or inputs.get(key) is None, f"missing:{key}"
