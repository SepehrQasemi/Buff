from __future__ import annotations

import pytest

from risk.types import RiskState
from selector.contract import (
    DisallowedStrategyError,
    SelectorInput,
    SelectorOutput,
    UnknownStrategyError,
)
from selector.records import selection_to_record
from selector.selector import select_strategy, select_strategy_contract


def test_selector_input_canonical_bytes_stable() -> None:
    input_a = SelectorInput(
        schema_version=1,
        market_state={"b": 1, "a": 2},
        risk_state="GREEN",
        allowed_strategy_ids=["TREND_FOLLOW", "MEAN_REVERT"],
        constraints={"y": 2, "x": 1},
    )
    input_b = SelectorInput(
        schema_version=1,
        market_state={"a": 2, "b": 1},
        risk_state="GREEN",
        allowed_strategy_ids=["MEAN_REVERT", "TREND_FOLLOW"],
        constraints={"x": 1, "y": 2},
    )
    assert input_a.canonical_bytes() == input_b.canonical_bytes()


def test_selector_output_canonical_bytes_stable() -> None:
    out_a = SelectorOutput(
        schema_version=1,
        chosen_strategy_id="TREND_FOLLOW",
        chosen_strategy_version=1,
        reason_codes=["rule:R2", "best_score"],
        audit_fields={"b": 2, "a": 1},
        tie_break="score_desc_strategy_id_asc_version_desc",
    )
    out_b = SelectorOutput(
        schema_version=1,
        chosen_strategy_id="TREND_FOLLOW",
        chosen_strategy_version=1,
        reason_codes=["rule:R2", "best_score"],
        audit_fields={"a": 1, "b": 2},
        tie_break="score_desc_strategy_id_asc_version_desc",
    )
    assert out_a.canonical_bytes() == out_b.canonical_bytes()


def test_selector_deterministic_same_input() -> None:
    selector_input = SelectorInput(
        schema_version=1,
        market_state={
            "trend_state": "up",
            "volatility_regime": "low",
            "momentum_state": "neutral",
            "structure_state": "breakout",
        },
        risk_state="GREEN",
        allowed_strategy_ids=["TREND_FOLLOW", "MEAN_REVERT", "DEFENSIVE"],
        constraints={},
    )
    out_a = select_strategy_contract(selector_input)
    out_b = select_strategy_contract(selector_input)
    assert out_a.to_dict() == out_b.to_dict()


def test_selector_tie_break_is_deterministic() -> None:
    selector_input = SelectorInput(
        schema_version=1,
        market_state={
            "trend_state": "unknown",
            "volatility_regime": "unknown",
            "momentum_state": "unknown",
            "structure_state": "unknown",
        },
        risk_state="GREEN",
        allowed_strategy_ids=["TREND_FOLLOW", "MEAN_REVERT"],
        constraints={"score_overrides": {"TREND_FOLLOW": 10, "MEAN_REVERT": 10}},
    )
    out = select_strategy_contract(selector_input)
    assert out.chosen_strategy_id == "MEAN_REVERT"
    assert out.tie_break == "score_desc_strategy_id_asc_version_desc"


def test_selector_rejects_unregistered_strategy() -> None:
    selector_input = SelectorInput(
        schema_version=1,
        market_state={
            "trend_state": "up",
            "volatility_regime": "low",
            "momentum_state": "neutral",
            "structure_state": "breakout",
        },
        risk_state="GREEN",
        allowed_strategy_ids=["UNKNOWN"],
        constraints={},
    )
    with pytest.raises(UnknownStrategyError):
        _ = select_strategy_contract(selector_input)


def test_selector_rejects_not_allowed_strategy() -> None:
    selector_input = SelectorInput(
        schema_version=1,
        market_state={
            "trend_state": "up",
            "volatility_regime": "low",
            "momentum_state": "neutral",
            "structure_state": "breakout",
        },
        risk_state="YELLOW",
        allowed_strategy_ids=["TREND_FOLLOW"],
        constraints={},
    )
    with pytest.raises(DisallowedStrategyError):
        _ = select_strategy_contract(selector_input)


def test_selector_selection_record_stable() -> None:
    signals = {
        "trend_state": "flat",
        "volatility_regime": "low",
        "momentum_state": "neutral",
        "structure_state": "meanrevert",
    }
    out_a = selection_to_record(select_strategy(signals, RiskState.GREEN))
    out_b = selection_to_record(select_strategy(signals, RiskState.GREEN))
    assert out_a == out_b
