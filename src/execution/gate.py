"""Centralized execution gate for risk veto."""

from __future__ import annotations

from dataclasses import dataclass

from audit.schema import AuditEvent
from risk.contracts import RiskInputs
from risk.contracts import RiskConfig, RiskDecision, RiskState
from risk.veto import risk_veto


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    decision: RiskDecision
    audit_event: AuditEvent
    reason: str | None


def gate_execution(inputs: RiskInputs, cfg: RiskConfig) -> GateResult:
    """Single integration point for risk veto before intent creation."""

    decision, audit_event = risk_veto(inputs, cfg)
    if decision.state == RiskState.RED:
        return GateResult(
            allowed=False,
            decision=decision,
            audit_event=audit_event,
            reason="risk_veto",
        )
    return GateResult(
        allowed=True,
        decision=decision,
        audit_event=audit_event,
        reason=None,
    )
