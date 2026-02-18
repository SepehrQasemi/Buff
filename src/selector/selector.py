from __future__ import annotations

from typing import Mapping

from risk.contracts import RiskState
from selector.contract import (
    DisallowedStrategyError,
    SelectorContractError,
    SelectorInput,
    SelectorOutput,
    UnknownStrategyError,
)
from selector.types import MarketSignals, SelectionResult
from strategies.menu import STRATEGY_MENU
from strategies.registry import StrategyRegistry


_MARKET_STATE_KEYS = ("trend_state", "volatility_regime", "momentum_state", "structure_state")


def _coerce_risk_state(value: RiskState | str) -> RiskState:
    if isinstance(value, RiskState):
        return value
    return RiskState(value)


def _normalize_market_state(signals: Mapping[str, object]) -> dict[str, object]:
    return {key: signals.get(key, "unknown") for key in _MARKET_STATE_KEYS}


def _allowed_for_risk_state(risk_state: RiskState) -> list[str]:
    allowed = [
        strategy_id
        for strategy_id, spec in STRATEGY_MENU.items()
        if risk_state in spec.allowed_risk_states
    ]
    return sorted(allowed)


def _legacy_reason_fields(
    chosen_strategy_id: str | None,
    market_state: Mapping[str, object],
    risk_state_value: str,
) -> tuple[str, str, dict[str, object]]:
    trend_state = market_state.get("trend_state", "unknown")
    volatility_regime = market_state.get("volatility_regime", "unknown")
    structure_state = market_state.get("structure_state", "unknown")

    if risk_state_value == RiskState.RED.value:
        return "R0", "risk=RED", {"risk_state": risk_state_value}
    if risk_state_value == RiskState.YELLOW.value:
        return "R1", "risk=YELLOW", {"risk_state": risk_state_value}
    if chosen_strategy_id in {"TREND_FOLLOW", "TREND_FOLLOW_V1"}:
        return (
            "R2",
            "trend+breakout & vol not high",
            {
                "risk_state": risk_state_value,
                "trend_state": trend_state,
                "volatility_regime": volatility_regime,
                "structure_state": structure_state,
            },
        )
    if chosen_strategy_id in {"MEAN_REVERT", "MEAN_REVERT_V1"}:
        return (
            "R3",
            "range+meanrevert & vol not high",
            {
                "risk_state": risk_state_value,
                "trend_state": trend_state,
                "volatility_regime": volatility_regime,
                "structure_state": structure_state,
            },
        )
    return "R9", "no_rule_matched", {"risk_state": risk_state_value}


def _score_strategy(
    *,
    strategy_id: str,
    market_state: Mapping[str, object],
    risk_state: RiskState,
    constraints: Mapping[str, object],
) -> int | None:
    overrides = constraints.get("score_overrides")
    if isinstance(overrides, Mapping) and strategy_id in overrides:
        value = overrides.get(strategy_id)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
        raise SelectorContractError("selector_score_override_invalid")

    if risk_state == RiskState.RED:
        return None
    if risk_state == RiskState.YELLOW:
        return 100 if strategy_id == "DEFENSIVE" else None

    trend_state = market_state.get("trend_state", "unknown")
    volatility_regime = market_state.get("volatility_regime", "unknown")
    structure_state = market_state.get("structure_state", "unknown")

    if strategy_id in {"TREND_FOLLOW", "TREND_FOLLOW_V1"}:
        if (
            trend_state in {"up", "down"}
            and volatility_regime in {"low", "mid"}
            and structure_state == "breakout"
        ):
            return 100
        return None
    if strategy_id in {"MEAN_REVERT", "MEAN_REVERT_V1"}:
        if (
            trend_state == "flat"
            and volatility_regime in {"low", "mid"}
            and structure_state == "meanrevert"
        ):
            return 90
        return None
    if strategy_id == "DEFENSIVE":
        return None
    return None


def _version_for_strategy(strategy_id: str, registry: StrategyRegistry | None) -> int:
    if registry is None:
        return 1
    spec = registry.strategies.get(strategy_id)
    if spec is None:
        return 1
    return spec.version


def select_strategy_contract(
    selector_input: SelectorInput,
    *,
    registry: StrategyRegistry | None = None,
    menu: Mapping[str, object] = STRATEGY_MENU,
) -> SelectorOutput:
    if selector_input.schema_version != 1:
        raise SelectorContractError("selector_schema_version_invalid")

    market_state = dict(selector_input.market_state)
    risk_state = _coerce_risk_state(selector_input.risk_state)
    allowed = list(selector_input.allowed_strategy_ids)
    constraints = dict(selector_input.constraints)

    if not allowed:
        rule_id, legacy_reason, legacy_inputs = _legacy_reason_fields(
            None, market_state, risk_state.value
        )
        return SelectorOutput(
            schema_version=1,
            chosen_strategy_id=None,
            chosen_strategy_version=None,
            reason_codes=[f"rule:{rule_id}", "no_selection"],
            audit_fields={
                "inputs_snapshot": legacy_inputs,
                "legacy_reason": legacy_reason,
                "legacy_rule_id": rule_id,
                "scores": [],
                "chosen_score": None,
                "tie_break": "no_allowed_strategies",
                "gates": {"risk_state": risk_state.value, "allowed_strategy_ids": []},
            },
            tie_break="no_allowed_strategies",
        )

    unknown = [strategy_id for strategy_id in allowed if strategy_id not in menu]
    if unknown:
        raise UnknownStrategyError("selector_unknown_strategy")

    if registry is not None:
        for strategy_id in allowed:
            if not registry.is_registered(strategy_id) or not registry.is_approved(strategy_id):
                raise UnknownStrategyError("selector_strategy_not_registered")

    for strategy_id in allowed:
        spec = menu.get(strategy_id)
        if spec is None:
            raise UnknownStrategyError("selector_unknown_strategy")
        allowed_states = getattr(spec, "allowed_risk_states", None)
        if allowed_states is None or risk_state not in allowed_states:
            raise DisallowedStrategyError("selector_strategy_disallowed")

    score_overrides = constraints.get("score_overrides")
    if isinstance(score_overrides, Mapping):
        for key in score_overrides.keys():
            if not isinstance(key, str):
                raise SelectorContractError("selector_score_override_invalid")
            if key not in allowed:
                raise UnknownStrategyError("selector_unknown_strategy")

    scored: list[dict[str, object]] = []
    for strategy_id in allowed:
        score = _score_strategy(
            strategy_id=strategy_id,
            market_state=market_state,
            risk_state=risk_state,
            constraints=constraints,
        )
        if score is None:
            continue
        scored.append(
            {
                "strategy_id": strategy_id,
                "score": score,
                "version": _version_for_strategy(strategy_id, registry),
            }
        )

    tie_break = "score_desc_strategy_id_asc_version_desc"
    if not scored:
        rule_id, legacy_reason, legacy_inputs = _legacy_reason_fields(
            None, market_state, risk_state.value
        )
        return SelectorOutput(
            schema_version=1,
            chosen_strategy_id=None,
            chosen_strategy_version=None,
            reason_codes=[f"rule:{rule_id}", "no_selection"],
            audit_fields={
                "inputs_snapshot": legacy_inputs,
                "legacy_reason": legacy_reason,
                "legacy_rule_id": rule_id,
                "scores": [],
                "chosen_score": None,
                "tie_break": "no_applicable_strategies",
                "gates": {"risk_state": risk_state.value, "allowed_strategy_ids": allowed},
            },
            tie_break="no_applicable_strategies",
        )

    def _sort_key(item: dict[str, object]) -> tuple[int, str, int]:
        score_val = int(item["score"])
        strategy_id = str(item["strategy_id"])
        version_val = int(item["version"])
        return (-score_val, strategy_id, -version_val)

    scored_sorted = sorted(scored, key=_sort_key)
    top_score = int(scored_sorted[0]["score"])
    tied = [item for item in scored_sorted if int(item["score"]) == top_score]

    chosen = sorted(tied, key=_sort_key)[0]
    chosen_strategy_id = str(chosen["strategy_id"])
    chosen_version = int(chosen["version"])

    rule_id, legacy_reason, legacy_inputs = _legacy_reason_fields(
        chosen_strategy_id, market_state, risk_state.value
    )

    reason_codes = [f"rule:{rule_id}", "best_score"]
    if len(tied) > 1:
        reason_codes.append("tie_break_strategy_id")

    return SelectorOutput(
        schema_version=1,
        chosen_strategy_id=chosen_strategy_id,
        chosen_strategy_version=chosen_version,
        reason_codes=reason_codes,
        audit_fields={
            "inputs_snapshot": legacy_inputs,
            "legacy_reason": legacy_reason,
            "legacy_rule_id": rule_id,
            "scores": scored_sorted,
            "chosen_score": top_score,
            "tie_break": tie_break,
            "gates": {"risk_state": risk_state.value, "allowed_strategy_ids": allowed},
        },
        tie_break=tie_break,
    )


def select_strategy(signals: MarketSignals, risk_state: RiskState) -> SelectionResult:
    risk_state_enum = _coerce_risk_state(risk_state)
    market_state = _normalize_market_state(signals)
    selector_input = SelectorInput(
        schema_version=1,
        market_state=market_state,
        risk_state=risk_state_enum.value,
        allowed_strategy_ids=_allowed_for_risk_state(risk_state_enum),
        constraints={},
    )
    output = select_strategy_contract(selector_input)
    legacy_reason = output.audit_fields.get("legacy_reason", "no_rule_matched")
    legacy_rule_id = output.audit_fields.get("legacy_rule_id", "R9")
    legacy_inputs = output.audit_fields.get(
        "inputs_snapshot", {"risk_state": risk_state_enum.value}
    )
    if not isinstance(legacy_inputs, dict):
        raise SelectorContractError("selector_audit_fields_invalid")
    if output.chosen_strategy_id is not None and output.chosen_strategy_id not in STRATEGY_MENU:
        raise UnknownStrategyError("selector_unknown_strategy")
    return SelectionResult(
        strategy_id=output.chosen_strategy_id,
        reason=str(legacy_reason),
        rule_id=str(legacy_rule_id),
        inputs=legacy_inputs,
    )
