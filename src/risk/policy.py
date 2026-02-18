"""Deterministic risk policy rules."""

from __future__ import annotations

from typing import Iterable

from risk.contracts import Permission, RiskConfig, RiskDecision, RiskInputs, RiskState


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


def _append_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def evaluate_policy(inputs: RiskInputs, config: RiskConfig) -> RiskDecision:
    """Evaluate risk policy for the latest metrics."""

    reasons: list[str] = []

    if inputs.invalid_index:
        _append_reason(reasons, "invalid_index")
    if not inputs.timestamps_valid:
        _append_reason(reasons, "invalid_timestamps")
    if inputs.invalid_close:
        _append_reason(reasons, "invalid_close")
    if inputs.missing_fraction > config.max_missing_fraction:
        _append_reason(reasons, "missing_fraction_exceeded")
    if not inputs.latest_metrics_valid:
        _append_reason(reasons, "missing_metrics")

    if reasons:
        state = RiskState.RED
        return RiskDecision(
            state=state,
            permission=_permission_for_state(state),
            recommended_scale=_scale_for_state(state, config),
            reasons=tuple(reasons),
        )

    atr_pct = inputs.atr_pct
    realized_vol = inputs.realized_vol

    if atr_pct is not None and atr_pct > config.red_atr_pct:
        _append_reason(reasons, "atr_pct_above_red")
    if realized_vol is not None and realized_vol > config.red_vol:
        _append_reason(reasons, "realized_vol_above_red")

    if reasons:
        state = RiskState.RED
        return RiskDecision(
            state=state,
            permission=_permission_for_state(state),
            recommended_scale=_scale_for_state(state, config),
            reasons=tuple(reasons),
        )

    yellow_flags: Iterable[tuple[float | None, float, float, str]] = (
        (atr_pct, config.yellow_atr_pct, config.red_atr_pct, "atr_pct_between_thresholds"),
        (
            realized_vol,
            config.yellow_vol,
            config.red_vol,
            "realized_vol_between_thresholds",
        ),
    )

    for value, yellow, red, label in yellow_flags:
        if value is not None and yellow <= value <= red:
            _append_reason(reasons, label)

    state = RiskState.YELLOW if reasons else RiskState.GREEN
    return RiskDecision(
        state=state,
        permission=_permission_for_state(state),
        recommended_scale=_scale_for_state(state, config),
        reasons=tuple(reasons),
    )
