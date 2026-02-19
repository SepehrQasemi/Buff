from __future__ import annotations

from importlib import import_module
import json
from pathlib import Path
import sys
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risk.rule_catalog import RiskRuleId
from risk.state_machine import RiskConfig, RiskState
from risk.veto import risk_veto


INVALID_INPUT_CASES: tuple[dict[str, object], ...] = (
    {},
    {"symbol": "BTCUSDT"},
    {
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "as_of": "not-a-timestamp",
        "atr_pct": -1.0,
        "realized_vol": 0.01,
        "missing_fraction": 0.0,
        "timestamps_valid": True,
        "latest_metrics_valid": True,
        "invalid_index": False,
        "invalid_close": False,
    },
)


def _config() -> RiskConfig:
    return RiskConfig(
        missing_red=0.2,
        atr_yellow=0.02,
        atr_red=0.05,
        rvol_yellow=0.02,
        rvol_red=0.05,
    )


def _valid_inputs() -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "as_of": "2024-01-01T00:00:00+00:00",
        "atr_pct": 0.01,
        "realized_vol": 0.01,
        "missing_fraction": 0.0,
        "timestamps_valid": True,
        "latest_metrics_valid": True,
        "invalid_index": False,
        "invalid_close": False,
    }


def _extract_rule_id(reason: object) -> str:
    attr_rule = getattr(reason, "rule_id", None)
    if isinstance(attr_rule, str) and attr_rule.strip():
        return attr_rule
    if isinstance(reason, dict):
        value = reason.get("rule_id")
        if isinstance(value, str) and value.strip():
            return value
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    return ""


def _resolve_policy_missing_rule_ids() -> set[str]:
    candidates = {RiskRuleId.RISK_POLICY_MISSING.value}
    for module_name in ("risk.state_machine", "risk.veto", "risk.contracts"):
        module = import_module(module_name)
        for name in dir(module):
            if "POLICY_MISSING" not in name:
                continue
            value = getattr(module, name)
            if isinstance(value, str) and value.strip():
                candidates.add(value.strip())
    return candidates


def _assert_reason_details_shape(reason_details: Any) -> None:
    assert isinstance(reason_details, list), "reason_details must be a list"
    for entry in reason_details:
        assert isinstance(entry, dict), "reason_details entries must be dicts"
        assert isinstance(entry.get("rule_id"), str) and entry["rule_id"], (
            "reason_details.rule_id missing"
        )
        assert isinstance(entry.get("severity"), str) and entry["severity"], (
            "reason_details.severity missing"
        )
        assert isinstance(entry.get("message"), str) and entry["message"], (
            "reason_details.message missing"
        )
        assert isinstance(entry.get("details"), dict), "reason_details.details must be dict"
    json.dumps(reason_details, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@pytest.mark.parametrize("invalid_inputs", INVALID_INPUT_CASES)
def test_s4_fail_closed_on_invalid_inputs(invalid_inputs: dict[str, object]) -> None:
    decision, audit_event = risk_veto(invalid_inputs, _config())

    assert decision.state is RiskState.RED
    assert decision.reasons
    rule_ids = {_extract_rule_id(reason) for reason in decision.reasons}
    rule_ids.discard("")
    assert rule_ids, "fail-closed decisions must include non-empty rule_id values"
    assert isinstance(decision.snapshot, dict) and decision.snapshot
    assert isinstance(decision.config_version, str) and decision.config_version
    assert isinstance(decision.inputs_digest, str) and decision.inputs_digest

    assert audit_event.component == "risk_veto"
    assert audit_event.action == "evaluate"
    assert audit_event.decision == RiskState.RED.value
    assert audit_event.reasons
    assert all(isinstance(reason, str) and reason for reason in audit_event.reasons)
    _assert_reason_details_shape(getattr(audit_event, "reason_details", []))
    assert isinstance(audit_event.snapshot, dict) and audit_event.snapshot


def test_s4_fail_closed_on_missing_policy_includes_policy_rule_id() -> None:
    decision, _audit_event = risk_veto(_valid_inputs(), None)  # type: ignore[arg-type]

    assert decision.state is RiskState.RED
    rule_ids = {_extract_rule_id(reason) for reason in decision.reasons}
    rule_ids.discard("")
    assert rule_ids, "missing-policy deny decision must include rule ids"

    expected_policy_ids = _resolve_policy_missing_rule_ids()
    assert rule_ids & expected_policy_ids, (
        f"expected one of policy-missing ids {sorted(expected_policy_ids)}, found {sorted(rule_ids)}"
    )
    assert RiskRuleId.RISK_POLICY_MISSING.value in rule_ids
