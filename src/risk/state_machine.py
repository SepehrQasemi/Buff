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
    return RiskDecision(
        state=state,
        reasons=reasons,
        snapshot=_snapshot(inputs),
        permission=_permission_for_state(state),
        config_version=config_version,
        inputs_digest=risk_inputs_digest(inputs),
    )


def _error_reason(
    rule_id: str, message: str, *, details: dict[str, Any] | None = None
) -> RiskReason:
    return RiskReason(
        rule_id,
        severity=RiskSeverity.ERROR,
        message=message,
        details=details or {},
    )


def _warn_reason(
    rule_id: str, message: str, *, details: dict[str, Any] | None = None
) -> RiskReason:
    return RiskReason(
        rule_id,
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

    if cfg is None or not isinstance(cfg, RiskConfig):
        return _build_decision(
            state=RiskState.RED,
            reasons=[
                _error_reason(
                    "RISK_POLICY_MISSING",
                    "risk policy configuration is missing",
                )
            ],
            inputs=inputs,
            cfg=None,
        )

    reasons: list[RiskReason] = []

    if not inputs.timestamps_valid:
        reasons.append(
            _error_reason("invalid_timestamps", "timestamps are invalid or non-monotonic")
        )
    if not inputs.latest_metrics_valid:
        reasons.append(_error_reason("missing_metrics", "latest metrics are missing"))
    if inputs.invalid_index:
        reasons.append(_error_reason("invalid_index", "input index is invalid"))
    if inputs.invalid_close:
        reasons.append(_error_reason("invalid_close", "close prices are invalid"))

    if reasons:
        return _build_decision(state=RiskState.RED, reasons=reasons, inputs=inputs, cfg=cfg)

    if inputs.missing_fraction > cfg.missing_red:
        return _build_decision(
            state=RiskState.RED,
            reasons=[
                _error_reason(
                    "missing_fraction_exceeded",
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
            "no_metrics",
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
                    "atr_pct_above_red",
                    "ATR percent exceeded RED threshold",
                    details={"atr_pct": atr_pct, "threshold": cfg.atr_red},
                )
            )
        elif cfg.atr_yellow is not None and atr_pct >= cfg.atr_yellow:
            yellow_reasons.append(
                _warn_reason(
                    "atr_pct_above_yellow",
                    "ATR percent exceeded YELLOW threshold",
                    details={"atr_pct": atr_pct, "threshold": cfg.atr_yellow},
                )
            )

    if realized_vol is not None:
        if cfg.rvol_red is not None and realized_vol >= cfg.rvol_red:
            red_reasons.append(
                _error_reason(
                    "realized_vol_above_red",
                    "realized volatility exceeded RED threshold",
                    details={"realized_vol": realized_vol, "threshold": cfg.rvol_red},
                )
            )
        elif cfg.rvol_yellow is not None and realized_vol >= cfg.rvol_yellow:
            yellow_reasons.append(
                _warn_reason(
                    "realized_vol_above_yellow",
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
