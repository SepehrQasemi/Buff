"""Types and configuration for risk permissioning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class RiskState(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class Permission(str, Enum):
    ALLOW = "ALLOW"
    RESTRICT = "RESTRICT"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class RiskConfig:
    """Configuration for risk policy thresholds and windows."""

    atr_feature: str = "atr_14"
    realized_vol_window: int = 20
    missing_lookback: int = 10
    max_missing_fraction: float = 0.2

    yellow_atr_pct: float = 0.01
    red_atr_pct: float = 0.02
    yellow_vol: float = 0.01
    red_vol: float = 0.02

    recommended_scale_yellow: float = 0.25

    def __post_init__(self) -> None:
        if self.realized_vol_window <= 0:
            raise ValueError("realized_vol_window must be > 0")
        if self.missing_lookback <= 0:
            raise ValueError("missing_lookback must be > 0")
        if not (0.0 <= self.max_missing_fraction <= 1.0):
            raise ValueError("max_missing_fraction must be in [0, 1]")
        if not (0.0 < self.yellow_atr_pct < self.red_atr_pct):
            raise ValueError("atr thresholds must satisfy 0 < yellow < red")
        if not (0.0 < self.yellow_vol < self.red_vol):
            raise ValueError("vol thresholds must satisfy 0 < yellow < red")
        if not (0.0 <= self.recommended_scale_yellow <= 1.0):
            raise ValueError("recommended_scale_yellow must be in [0, 1]")


@dataclass(frozen=True)
class RiskInputs:
    atr_pct: float | None
    realized_vol: float | None
    missing_fraction: float
    timestamps_valid: bool
    latest_metrics_valid: bool


@dataclass(frozen=True)
class RiskDecision:
    state: RiskState
    permission: Permission
    recommended_scale: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RiskContext:
    run_id: str | None = None
    workspace: str | None = None
    symbol: str | None = None
    timeframe: str | None = None


def threshold_snapshot(config: RiskConfig) -> Mapping[str, float]:
    return {
        "yellow_atr_pct": config.yellow_atr_pct,
        "red_atr_pct": config.red_atr_pct,
        "yellow_vol": config.yellow_vol,
        "red_vol": config.red_vol,
        "max_missing_fraction": config.max_missing_fraction,
        "missing_lookback": float(config.missing_lookback),
        "realized_vol_window": float(config.realized_vol_window),
    }
