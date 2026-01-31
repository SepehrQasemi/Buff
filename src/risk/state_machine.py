"""Deterministic risk state machine (GREEN/YELLOW/RED)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from risk.contracts import RiskInputs


class RiskState(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass(frozen=True)
class RiskDecision:
    state: RiskState
    reasons: list[str]
    snapshot: dict[str, Any]


@dataclass(frozen=True)
class RiskConfig:
    missing_red: float
    atr_yellow: float | None = None
    atr_red: float | None = None
    rvol_yellow: float | None = None
    rvol_red: float | None = None
    no_metrics_state: RiskState = RiskState.YELLOW

    def __post_init__(self) -> None:
        if not 0.0 <= self.missing_red <= 1.0:
            raise ValueError("missing_red must be in [0, 1]")
        if self.atr_yellow is not None and self.atr_red is not None:
            if self.atr_yellow > self.atr_red:
                raise ValueError("atr_yellow must be <= atr_red")
        if self.rvol_yellow is not None and self.rvol_red is not None:
            if self.rvol_yellow > self.rvol_red:
                raise ValueError("rvol_yellow must be <= rvol_red")
        if not isinstance(self.no_metrics_state, RiskState):
            raise ValueError("no_metrics_state must be a RiskState")


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

    reasons: list[str] = []

    if not inputs.timestamps_valid:
        reasons.append("invalid_timestamps")
    if not inputs.latest_metrics_valid:
        reasons.append("missing_metrics")
    if inputs.invalid_index:
        reasons.append("invalid_index")
    if inputs.invalid_close:
        reasons.append("invalid_close")

    if reasons:
        return RiskDecision(RiskState.RED, reasons, _snapshot(inputs))

    if inputs.missing_fraction > cfg.missing_red:
        return RiskDecision(
            RiskState.RED, ["missing_fraction_exceeded"], _snapshot(inputs)
        )

    atr_pct = inputs.atr_pct
    realized_vol = inputs.realized_vol

    if atr_pct is None and realized_vol is None:
        return RiskDecision(cfg.no_metrics_state, ["no_metrics"], _snapshot(inputs))

    red_reasons: list[str] = []
    yellow_reasons: list[str] = []

    if atr_pct is not None:
        if cfg.atr_red is not None and atr_pct >= cfg.atr_red:
            red_reasons.append("atr_pct_above_red")
        elif cfg.atr_yellow is not None and atr_pct >= cfg.atr_yellow:
            yellow_reasons.append("atr_pct_above_yellow")

    if realized_vol is not None:
        if cfg.rvol_red is not None and realized_vol >= cfg.rvol_red:
            red_reasons.append("realized_vol_above_red")
        elif cfg.rvol_yellow is not None and realized_vol >= cfg.rvol_yellow:
            yellow_reasons.append("realized_vol_above_yellow")

    if red_reasons:
        return RiskDecision(RiskState.RED, red_reasons, _snapshot(inputs))
    if yellow_reasons:
        return RiskDecision(RiskState.YELLOW, yellow_reasons, _snapshot(inputs))
    return RiskDecision(RiskState.GREEN, [], _snapshot(inputs))
