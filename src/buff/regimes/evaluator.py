"""Evaluate regime rules against a feature snapshot."""

from __future__ import annotations

import math
from typing import Any, Mapping

from buff.regimes.errors import RegimeEvaluationError
from buff.regimes.schema import Condition
from buff.regimes.types import RegimeConfig, RegimeDecision


def evaluate_regime(
    features: Mapping[str, Any],
    config: RegimeConfig,
) -> RegimeDecision:
    resolved, missing = _resolve_required_features(features, config)
    if missing:
        return _fail_closed(config, missing)

    for regime in config.regimes:
        if regime.conditions is None:
            return RegimeDecision(
                regime_id=regime.regime_id,
                matched_conditions_summary="default_match",
                allowed_strategy_families=regime.allowed_strategy_families,
                forbidden_strategy_families=regime.forbidden_strategy_families,
                risk_modifiers=regime.risk_modifiers,
            )
        matched, summary = _evaluate_condition(regime.conditions, resolved)
        if matched:
            return RegimeDecision(
                regime_id=regime.regime_id,
                matched_conditions_summary=summary,
                allowed_strategy_families=regime.allowed_strategy_families,
                forbidden_strategy_families=regime.forbidden_strategy_families,
                risk_modifiers=regime.risk_modifiers,
            )

    raise RegimeEvaluationError("no_regime_matched")


def _fail_closed(config: RegimeConfig, missing: list[str]) -> RegimeDecision:
    risk_off = next((regime for regime in config.regimes if regime.regime_id == "RISK_OFF"), None)
    if risk_off is None:
        raise RegimeEvaluationError("risk_off_missing")
    summary = "missing_features:" + ",".join(sorted(missing))
    return RegimeDecision(
        regime_id=risk_off.regime_id,
        matched_conditions_summary=summary,
        allowed_strategy_families=risk_off.allowed_strategy_families,
        forbidden_strategy_families=risk_off.forbidden_strategy_families,
        risk_modifiers=risk_off.risk_modifiers,
    )


def _resolve_required_features(
    features: Mapping[str, Any],
    config: RegimeConfig,
) -> tuple[dict[str, float], list[str]]:
    resolved: dict[str, float] = {}
    missing: list[str] = []
    for name in config.required_features:
        value = _resolve_feature_value(name, features, config)
        if value is None:
            missing.append(name)
            continue
        resolved[name] = value
    return resolved, missing


def _resolve_feature_value(
    name: str,
    features: Mapping[str, Any],
    config: RegimeConfig,
) -> float | None:
    value = _coerce_numeric(features.get(name))
    if value is not None:
        return value

    canonical = config.alias_to_canonical.get(name)
    if canonical:
        value = _coerce_numeric(features.get(canonical))
        if value is not None:
            return value
        for alias in config.feature_aliases.get(canonical, ()):  # type: ignore[arg-type]
            value = _coerce_numeric(features.get(alias))
            if value is not None:
                return value

    for alias in config.feature_aliases.get(name, ()):  # type: ignore[arg-type]
        value = _coerce_numeric(features.get(alias))
        if value is not None:
            return value

    return None


def _coerce_numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    else:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
    if math.isnan(numeric):
        return None
    return numeric


def _evaluate_condition(condition: Condition, values: Mapping[str, float]) -> tuple[bool, str]:
    op = condition.op
    if op in {"gt", "gte", "lt", "lte", "abs_gt"}:
        return _evaluate_numeric(condition, values)
    if op == "between":
        return _evaluate_between(condition, values)
    if op in {"all", "any"}:
        return _evaluate_group(condition, values)
    if op == "not":
        return _evaluate_not(condition, values)
    raise RegimeEvaluationError(f"condition_operator_unknown:{op}")


def _evaluate_numeric(condition: Condition, values: Mapping[str, float]) -> tuple[bool, str]:
    feature = _require_feature(condition)
    threshold = _require_value(condition)
    actual = values[feature]
    if condition.op == "gt":
        matched = actual > threshold
        desc = f"gt({feature}={_fmt(actual)}, threshold={_fmt(threshold)})"
    elif condition.op == "gte":
        matched = actual >= threshold
        desc = f"gte({feature}={_fmt(actual)}, threshold={_fmt(threshold)})"
    elif condition.op == "lt":
        matched = actual < threshold
        desc = f"lt({feature}={_fmt(actual)}, threshold={_fmt(threshold)})"
    elif condition.op == "lte":
        matched = actual <= threshold
        desc = f"lte({feature}={_fmt(actual)}, threshold={_fmt(threshold)})"
    elif condition.op == "abs_gt":
        matched = abs(actual) > threshold
        desc = f"abs_gt({feature}={_fmt(actual)}, threshold={_fmt(threshold)})"
    else:
        raise RegimeEvaluationError(f"condition_operator_unknown:{condition.op}")
    return matched, _with_result(desc, matched)


def _evaluate_between(condition: Condition, values: Mapping[str, float]) -> tuple[bool, str]:
    feature = _require_feature(condition)
    lower = _require_lower(condition)
    upper = _require_upper(condition)
    actual = values[feature]
    matched = lower <= actual <= upper
    desc = f"between({feature}={_fmt(actual)}, range=[{_fmt(lower)},{_fmt(upper)}])"
    return matched, _with_result(desc, matched)


def _evaluate_group(condition: Condition, values: Mapping[str, float]) -> tuple[bool, str]:
    results: list[tuple[bool, str]] = []
    for item in condition.items:
        results.append(_evaluate_condition(item, values))
    if condition.op == "all":
        matched = all(result for result, _ in results)
    else:
        matched = any(result for result, _ in results)
    joined = ", ".join(desc for _, desc in results)
    desc = f"{condition.op}([{joined}])"
    return matched, _with_result(desc, matched)


def _evaluate_not(condition: Condition, values: Mapping[str, float]) -> tuple[bool, str]:
    if not condition.items:
        raise RegimeEvaluationError("condition_not_empty")
    matched_child, desc_child = _evaluate_condition(condition.items[0], values)
    matched = not matched_child
    desc = f"not({desc_child})"
    return matched, _with_result(desc, matched)


def _require_feature(condition: Condition) -> str:
    if condition.feature is None:
        raise RegimeEvaluationError("condition_feature_missing")
    return condition.feature


def _require_value(condition: Condition) -> float:
    if condition.value is None:
        raise RegimeEvaluationError("condition_value_missing")
    return condition.value


def _require_lower(condition: Condition) -> float:
    if condition.lower is None:
        raise RegimeEvaluationError("condition_lower_missing")
    return condition.lower


def _require_upper(condition: Condition) -> float:
    if condition.upper is None:
        raise RegimeEvaluationError("condition_upper_missing")
    return condition.upper


def _with_result(desc: str, matched: bool) -> str:
    return f"{desc}=>{matched}"


def _fmt(value: float) -> str:
    return f"{value:.6g}"
