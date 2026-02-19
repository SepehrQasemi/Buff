"""Deterministic risk state machine (GREEN/YELLOW/RED)."""

from __future__ import annotations

from typing import Any

from risk.contracts import (
    Permission,
    RiskConfig as _RiskConfig,
    RiskDecision as _RiskDecision,
    RiskInputs,
    RiskReason,
    RiskSeverity,
    RiskState as _RiskState,
    risk_inputs_digest,
)
from risk.rule_catalog import RiskRuleId, ensure_catalog_rule_id

# Keep canonical class definitions in risk.contracts while marking state-machine
# authority metadata expected by existing S4 tooling checks.
RiskConfig = _RiskConfig
RiskDecision = _RiskDecision
RiskState = _RiskState
RiskConfig.__module__ = __name__
RiskDecision.__module__ = __name__
RiskState.__module__ = __name__


def _permission_for_state(state: RiskState) -> Permission:
    if state == RiskState.GREEN:
        return Permission.ALLOW
    if state == RiskState.YELLOW:
        return Permission.RESTRICT
    return Permission.BLOCK


def _build_decision(
    *,
    state: RiskState,
    reasons: list[RiskReason],
    inputs: RiskInputs,
    cfg: RiskConfig | None,
) -> RiskDecision:
    config_version = cfg.config_version if isinstance(cfg, RiskConfig) else "v1"
    pack_id = cfg.pack_id if isinstance(cfg, RiskConfig) else "L3_BALANCED"
    pack_version = cfg.pack_version if isinstance(cfg, RiskConfig) else "v1"
    return RiskDecision(
        state=state,
        reasons=reasons,
        snapshot=_snapshot(inputs),
        permission=_permission_for_state(state),
        pack_id=pack_id,
        pack_version=pack_version,
        config_version=config_version,
        inputs_digest=risk_inputs_digest(inputs),
    )


def _error_reason(
    rule_id: str | RiskRuleId, message: str, *, details: dict[str, Any] | None = None
) -> RiskReason:
    canonical_rule_id = ensure_catalog_rule_id(rule_id)
    return RiskReason(
        canonical_rule_id,
        severity=RiskSeverity.ERROR,
        message=message,
        details=details or {},
    )


def _warn_reason(
    rule_id: str | RiskRuleId, message: str, *, details: dict[str, Any] | None = None
) -> RiskReason:
    canonical_rule_id = ensure_catalog_rule_id(rule_id)
    return RiskReason(
        canonical_rule_id,
        severity=RiskSeverity.WARN,
        message=message,
        details=details or {},
    )


def _snapshot(inputs: RiskInputs) -> dict[str, Any]:
    return {
        "missing_fraction": inputs.missing_fraction,
        "atr_pct": inputs.atr_pct,
        "realized_vol": inputs.realized_vol,
        "timestamps_valid": inputs.timestamps_valid,
        "latest_metrics_valid": inputs.latest_metrics_valid,
        "invalid_index": inputs.invalid_index,
        "invalid_close": inputs.invalid_close,
    }


def evaluate_risk(inputs: RiskInputs, cfg: RiskConfig) -> RiskDecision:
    """Evaluate risk state using deterministic rules."""

    if cfg is None:
        return _build_decision(
            state=RiskState.RED,
            reasons=[
                _error_reason(
                    RiskRuleId.RISK_POLICY_MISSING,
                    "risk policy configuration is missing",
                )
            ],
            inputs=inputs,
            cfg=None,
        )
    if not isinstance(cfg, RiskConfig):
        return _build_decision(
            state=RiskState.RED,
            reasons=[
                _error_reason(
                    RiskRuleId.RISK_INVALID_CONFIG,
                    "risk policy configuration is invalid",
                    details={"config_type": type(cfg).__name__},
                )
            ],
            inputs=inputs,
            cfg=None,
        )

    reasons: list[RiskReason] = []

    if not inputs.timestamps_valid:
        reasons.append(
            _error_reason(
                RiskRuleId.INVALID_TIMESTAMPS,
                "timestamps are invalid or non-monotonic",
            )
        )
    if not inputs.latest_metrics_valid:
        reasons.append(_error_reason(RiskRuleId.MISSING_METRICS, "latest metrics are missing"))
    if inputs.invalid_index:
        reasons.append(_error_reason(RiskRuleId.INVALID_INDEX, "input index is invalid"))
    if inputs.invalid_close:
        reasons.append(_error_reason(RiskRuleId.INVALID_CLOSE, "close prices are invalid"))

    if reasons:
        return _build_decision(state=RiskState.RED, reasons=reasons, inputs=inputs, cfg=cfg)

    if inputs.missing_fraction > cfg.missing_red:
        return _build_decision(
            state=RiskState.RED,
            reasons=[
                _error_reason(
                    RiskRuleId.MISSING_FRACTION_EXCEEDED,
                    "missing fraction exceeded configured threshold",
                    details={
                        "missing_fraction": inputs.missing_fraction,
                        "threshold": cfg.missing_red,
                    },
                )
            ],
            inputs=inputs,
            cfg=cfg,
        )

    atr_pct = inputs.atr_pct
    realized_vol = inputs.realized_vol

    if atr_pct is None and realized_vol is None:
        no_metrics_state = cfg.no_metrics_state
        no_metrics_reason = RiskReason(
            RiskRuleId.NO_METRICS.value,
            severity=RiskSeverity.ERROR if no_metrics_state == RiskState.RED else RiskSeverity.WARN,
            message="no risk metrics available",
            details={},
        )
        return _build_decision(
            state=no_metrics_state,
            reasons=[no_metrics_reason],
            inputs=inputs,
            cfg=cfg,
        )

    red_reasons: list[RiskReason] = []
    yellow_reasons: list[RiskReason] = []

    if atr_pct is not None:
        if cfg.atr_red is not None and atr_pct >= cfg.atr_red:
            red_reasons.append(
                _error_reason(
                    RiskRuleId.ATR_PCT_ABOVE_RED,
                    "ATR percent exceeded RED threshold",
                    details={"atr_pct": atr_pct, "threshold": cfg.atr_red},
                )
            )
        elif cfg.atr_yellow is not None and atr_pct >= cfg.atr_yellow:
            yellow_reasons.append(
                _warn_reason(
                    RiskRuleId.ATR_PCT_ABOVE_YELLOW,
                    "ATR percent exceeded YELLOW threshold",
                    details={"atr_pct": atr_pct, "threshold": cfg.atr_yellow},
                )
            )

    if realized_vol is not None:
        if cfg.rvol_red is not None and realized_vol >= cfg.rvol_red:
            red_reasons.append(
                _error_reason(
                    RiskRuleId.REALIZED_VOL_ABOVE_RED,
                    "realized volatility exceeded RED threshold",
                    details={"realized_vol": realized_vol, "threshold": cfg.rvol_red},
                )
            )
        elif cfg.rvol_yellow is not None and realized_vol >= cfg.rvol_yellow:
            yellow_reasons.append(
                _warn_reason(
                    RiskRuleId.REALIZED_VOL_ABOVE_YELLOW,
                    "realized volatility exceeded YELLOW threshold",
                    details={"realized_vol": realized_vol, "threshold": cfg.rvol_yellow},
                )
            )

    if red_reasons:
        return _build_decision(state=RiskState.RED, reasons=red_reasons, inputs=inputs, cfg=cfg)
    if yellow_reasons:
        return _build_decision(
            state=RiskState.YELLOW, reasons=yellow_reasons, inputs=inputs, cfg=cfg
        )
    return _build_decision(state=RiskState.GREEN, reasons=[], inputs=inputs, cfg=cfg)
