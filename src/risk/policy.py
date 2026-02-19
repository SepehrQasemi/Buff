"""Deterministic risk policy rules."""

from __future__ import annotations

from typing import Iterable

from risk.contracts import (
    Permission,
    RiskConfig,
    RiskDecision,
    RiskInputs,
    RiskReason,
    RiskSeverity,
    RiskState,
    risk_inputs_digest,
)
from risk.rule_catalog import RiskRuleId


def _permission_for_state(state: RiskState) -> Permission:
    if state == RiskState.GREEN:
        return Permission.ALLOW
    if state == RiskState.YELLOW:
        return Permission.RESTRICT
    return Permission.BLOCK


def _scale_for_state(state: RiskState, config: RiskConfig) -> float:
    if state == RiskState.GREEN:
        return 1.0
    if state == RiskState.YELLOW:
        return config.recommended_scale_yellow
    return 0.0


def _append_reason(
    reasons: list[RiskReason],
    *,
    rule_id: str,
    severity: RiskSeverity,
    message: str,
) -> None:
    if any(reason.rule_id == rule_id for reason in reasons):
        return
    reasons.append(RiskReason(rule_id, severity=severity, message=message))


def evaluate_policy(inputs: RiskInputs, config: RiskConfig) -> RiskDecision:
    """Evaluate risk policy for the latest metrics."""

    reasons: list[RiskReason] = []

    if inputs.invalid_index:
        _append_reason(
            reasons,
            rule_id=RiskRuleId.INVALID_INDEX.value,
            severity=RiskSeverity.ERROR,
            message="input index is invalid",
        )
    if not inputs.timestamps_valid:
        _append_reason(
            reasons,
            rule_id=RiskRuleId.INVALID_TIMESTAMPS.value,
            severity=RiskSeverity.ERROR,
            message="timestamps are invalid or non-monotonic",
        )
    if inputs.invalid_close:
        _append_reason(
            reasons,
            rule_id=RiskRuleId.INVALID_CLOSE.value,
            severity=RiskSeverity.ERROR,
            message="close prices are invalid",
        )
    if inputs.missing_fraction > config.max_missing_fraction:
        _append_reason(
            reasons,
            rule_id=RiskRuleId.MISSING_FRACTION_EXCEEDED.value,
            severity=RiskSeverity.ERROR,
            message="missing fraction exceeded configured threshold",
        )
    if not inputs.latest_metrics_valid:
        _append_reason(
            reasons,
            rule_id=RiskRuleId.MISSING_METRICS.value,
            severity=RiskSeverity.ERROR,
            message="latest metrics are missing",
        )

    if reasons:
        state = RiskState.RED
        return RiskDecision(
            state=state,
            permission=_permission_for_state(state),
            recommended_scale=_scale_for_state(state, config),
            reasons=tuple(reasons),
            pack_id=config.pack_id,
            pack_version=config.pack_version,
            config_version=config.config_version,
            inputs_digest=risk_inputs_digest(inputs),
        )

    atr_pct = inputs.atr_pct
    realized_vol = inputs.realized_vol

    if atr_pct is not None and atr_pct > config.red_atr_pct:
        _append_reason(
            reasons,
            rule_id=RiskRuleId.ATR_PCT_ABOVE_RED.value,
            severity=RiskSeverity.ERROR,
            message="ATR percent exceeded RED threshold",
        )
    if realized_vol is not None and realized_vol > config.red_vol:
        _append_reason(
            reasons,
            rule_id=RiskRuleId.REALIZED_VOL_ABOVE_RED.value,
            severity=RiskSeverity.ERROR,
            message="realized volatility exceeded RED threshold",
        )

    if reasons:
        state = RiskState.RED
        return RiskDecision(
            state=state,
            permission=_permission_for_state(state),
            recommended_scale=_scale_for_state(state, config),
            reasons=tuple(reasons),
            pack_id=config.pack_id,
            pack_version=config.pack_version,
            config_version=config.config_version,
            inputs_digest=risk_inputs_digest(inputs),
        )

    yellow_flags: Iterable[tuple[float | None, float, float, str]] = (
        (
            atr_pct,
            config.yellow_atr_pct,
            config.red_atr_pct,
            RiskRuleId.ATR_PCT_BETWEEN_THRESHOLDS.value,
        ),
        (
            realized_vol,
            config.yellow_vol,
            config.red_vol,
            RiskRuleId.REALIZED_VOL_BETWEEN_THRESHOLDS.value,
        ),
    )

    for value, yellow, red, label in yellow_flags:
        if value is not None and yellow <= value <= red:
            _append_reason(
                reasons,
                rule_id=label,
                severity=RiskSeverity.WARN,
                message=f"{label} threshold warning",
            )

    state = RiskState.YELLOW if reasons else RiskState.GREEN
    return RiskDecision(
        state=state,
        permission=_permission_for_state(state),
        recommended_scale=_scale_for_state(state, config),
        reasons=tuple(reasons),
        pack_id=config.pack_id,
        pack_version=config.pack_version,
        config_version=config.config_version,
        inputs_digest=risk_inputs_digest(inputs),
    )
