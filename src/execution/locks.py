from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLocks:
    max_exposure: float
    max_trades_per_day: int
    leverage_cap: float
    kill_switch: bool
    mandatory_protective_exit: bool


@dataclass(frozen=True)
class RiskLockStatus:
    allowed: bool
    reason: str


def evaluate_locks(
    locks: RiskLocks,
    current_exposure: float | None,
    trades_today: int | None,
    leverage: float | None,
    protective_exit_required: bool,
) -> RiskLockStatus:
    if locks.kill_switch:
        return RiskLockStatus(False, "kill_switch")
    if current_exposure is None or trades_today is None or leverage is None:
        return RiskLockStatus(False, "missing_risk_limits")
    if current_exposure > locks.max_exposure:
        return RiskLockStatus(False, "max_exposure_exceeded")
    if trades_today >= locks.max_trades_per_day:
        return RiskLockStatus(False, "max_trades_exceeded")
    if leverage > locks.leverage_cap:
        return RiskLockStatus(False, "leverage_cap_exceeded")
    if locks.mandatory_protective_exit and not protective_exit_required:
        return RiskLockStatus(False, "protective_exit_required")
    return RiskLockStatus(True, "ok")
