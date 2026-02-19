"""Canonical risk rule taxonomy (authoritative rule IDs)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from risk.contracts import RiskSeverity


class RiskRuleId(str, Enum):
    # Mandatory S4 taxonomy anchors.
    RISK_POLICY_MISSING = "RISK_POLICY_MISSING"
    RISK_INVALID_CONFIG = "RISK_INVALID_CONFIG"
    RISK_INPUTS_INVALID = "invalid_inputs"
    RISK_EXPOSURE_LIMIT = "RISK_EXPOSURE_LIMIT"
    RISK_DRAWDOWN_LIMIT = "RISK_DRAWDOWN_LIMIT"

    # Active state-machine / veto reasons.
    INVALID_TIMESTAMPS = "invalid_timestamps"
    MISSING_METRICS = "missing_metrics"
    INVALID_INDEX = "invalid_index"
    INVALID_CLOSE = "invalid_close"
    MISSING_FRACTION_EXCEEDED = "missing_fraction_exceeded"
    NO_METRICS = "no_metrics"
    ATR_PCT_BETWEEN_THRESHOLDS = "atr_pct_between_thresholds"
    REALIZED_VOL_BETWEEN_THRESHOLDS = "realized_vol_between_thresholds"
    ATR_PCT_ABOVE_YELLOW = "atr_pct_above_yellow"
    ATR_PCT_ABOVE_RED = "atr_pct_above_red"
    REALIZED_VOL_ABOVE_YELLOW = "realized_vol_above_yellow"
    REALIZED_VOL_ABOVE_RED = "realized_vol_above_red"
    RISK_AUDIT_ERROR = "audit_error"
    RISK_EVALUATION_ERROR = "risk_evaluation_error"


@dataclass(frozen=True)
class RuleMeta:
    severity: RiskSeverity
    description: str


RULE_METADATA: Final[dict[RiskRuleId, RuleMeta]] = {
    RiskRuleId.RISK_POLICY_MISSING: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Risk policy/config is missing.",
    ),
    RiskRuleId.RISK_INVALID_CONFIG: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Risk policy config is present but invalid.",
    ),
    RiskRuleId.RISK_INPUTS_INVALID: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Risk inputs validation failed.",
    ),
    RiskRuleId.RISK_EXPOSURE_LIMIT: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Exposure limit exceeded.",
    ),
    RiskRuleId.RISK_DRAWDOWN_LIMIT: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Drawdown limit exceeded.",
    ),
    RiskRuleId.INVALID_TIMESTAMPS: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Input timestamps are invalid or non-monotonic.",
    ),
    RiskRuleId.MISSING_METRICS: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Required risk metrics are missing.",
    ),
    RiskRuleId.INVALID_INDEX: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Input index is invalid.",
    ),
    RiskRuleId.INVALID_CLOSE: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Close prices are invalid.",
    ),
    RiskRuleId.MISSING_FRACTION_EXCEEDED: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Missing-data fraction exceeded threshold.",
    ),
    RiskRuleId.NO_METRICS: RuleMeta(
        severity=RiskSeverity.WARN,
        description="No risk metrics available.",
    ),
    RiskRuleId.ATR_PCT_BETWEEN_THRESHOLDS: RuleMeta(
        severity=RiskSeverity.WARN,
        description="ATR percent is between YELLOW and RED thresholds.",
    ),
    RiskRuleId.REALIZED_VOL_BETWEEN_THRESHOLDS: RuleMeta(
        severity=RiskSeverity.WARN,
        description="Realized volatility is between YELLOW and RED thresholds.",
    ),
    RiskRuleId.ATR_PCT_ABOVE_YELLOW: RuleMeta(
        severity=RiskSeverity.WARN,
        description="ATR percent above YELLOW threshold.",
    ),
    RiskRuleId.ATR_PCT_ABOVE_RED: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="ATR percent above RED threshold.",
    ),
    RiskRuleId.REALIZED_VOL_ABOVE_YELLOW: RuleMeta(
        severity=RiskSeverity.WARN,
        description="Realized volatility above YELLOW threshold.",
    ),
    RiskRuleId.REALIZED_VOL_ABOVE_RED: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Realized volatility above RED threshold.",
    ),
    RiskRuleId.RISK_AUDIT_ERROR: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Risk audit emission failed.",
    ),
    RiskRuleId.RISK_EVALUATION_ERROR: RuleMeta(
        severity=RiskSeverity.ERROR,
        description="Risk evaluation failed unexpectedly.",
    ),
}


ALL_RULE_IDS: Final[frozenset[str]] = frozenset(rule.value for rule in RiskRuleId)


def ensure_catalog_rule_id(rule_id: str | RiskRuleId) -> str:
    if isinstance(rule_id, RiskRuleId):
        return rule_id.value
    try:
        return RiskRuleId(rule_id).value
    except ValueError as exc:
        raise ValueError(f"unknown_risk_rule_id:{rule_id}") from exc
