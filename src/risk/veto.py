"""Risk veto integration point."""

from __future__ import annotations

from typing import Any

from audit.schema import AuditEvent, make_audit_event
from risk.contracts import RiskInputs, validate_risk_inputs
from risk.state_machine import RiskConfig, RiskDecision, RiskState, evaluate_risk


def _invalid_decision(snapshot: dict[str, Any] | None = None) -> RiskDecision:
    return RiskDecision(
        state=RiskState.RED,
        reasons=["invalid_inputs"],
        snapshot=snapshot or {"invalid": True},
    )


def risk_veto(inputs: RiskInputs, cfg: RiskConfig) -> tuple[RiskDecision, AuditEvent]:
    """
    Returns (decision, audit_event).
    Fail-closed: if anything raises or invalid -> RED with reason 'invalid_inputs'.
    """

    try:
        validated = validate_risk_inputs(inputs)
        decision = evaluate_risk(validated, cfg)
        audit_event = make_audit_event(component="risk_veto", action="evaluate", decision=decision)
        return decision, audit_event
    except Exception:
        decision = _invalid_decision()
        try:
            audit_event = make_audit_event(
                component="risk_veto", action="evaluate", decision=decision
            )
        except Exception:
            audit_event = AuditEvent(
                event_id="invalid",
                ts_utc="1970-01-01T00:00:00Z",
                component="risk_veto",
                action="evaluate",
                inputs_hash="",
                decision=RiskState.RED.value,
                reasons=list(decision.reasons),
                snapshot=decision.snapshot,
            )
        return decision, audit_event
