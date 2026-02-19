"""Risk veto integration point."""

from __future__ import annotations

from typing import Any

from audit.schema import AuditEvent, make_audit_event
from risk.contracts import (
    Permission,
    RiskConfig,
    RiskDecision,
    RiskInputs,
    RiskReason,
    RiskSeverity,
    RiskState,
    reason_codes,
    reason_payloads,
    risk_inputs_digest,
    validate_risk_inputs,
)
from risk.rule_catalog import RiskRuleId, ensure_catalog_rule_id
from risk.state_machine import evaluate_risk


def _fail_closed_decision(
    *,
    cfg: RiskConfig | None,
    rule_id: str | RiskRuleId,
    message: str,
    snapshot: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> RiskDecision:
    canonical_rule_id = ensure_catalog_rule_id(rule_id)
    snapshot_payload = snapshot or {"invalid": True}
    config_version = cfg.config_version if isinstance(cfg, RiskConfig) else "v1"
    pack_id = cfg.pack_id if isinstance(cfg, RiskConfig) else "L3_BALANCED"
    pack_version = cfg.pack_version if isinstance(cfg, RiskConfig) else "v1"
    return RiskDecision(
        state=RiskState.RED,
        permission=Permission.BLOCK,
        reasons=[
            RiskReason(
                canonical_rule_id,
                severity=RiskSeverity.ERROR,
                message=message,
                details=details or {},
            )
        ],
        snapshot=snapshot_payload,
        pack_id=pack_id,
        pack_version=pack_version,
        config_version=config_version,
        inputs_digest=risk_inputs_digest(snapshot_payload),
    )


def _fallback_audit_event(decision: RiskDecision) -> AuditEvent:
    return AuditEvent(
        event_id="invalid",
        ts_utc="1970-01-01T00:00:00Z",
        component="risk_veto",
        action="evaluate",
        inputs_hash="",
        decision=RiskState.RED.value,
        reasons=reason_codes(decision.reasons),
        reason_details=reason_payloads(decision.reasons),
        snapshot=decision.snapshot,
        config_version=decision.config_version,
        inputs_digest=decision.inputs_digest,
    )


def risk_veto(inputs: RiskInputs, cfg: RiskConfig) -> tuple[RiskDecision, AuditEvent]:
    """
    Returns (decision, audit_event).
    Fail-closed: if anything raises or invalid -> RED with canonical catalog rule.
    """

    try:
        validated = validate_risk_inputs(inputs)
    except Exception:
        decision = _fail_closed_decision(
            cfg=cfg,
            rule_id=RiskRuleId.RISK_INPUTS_INVALID,
            message="risk inputs failed validation",
        )
        return decision, _fallback_audit_event(decision)

    try:
        decision = evaluate_risk(validated, cfg)
    except Exception:
        rule_id = (
            RiskRuleId.RISK_POLICY_MISSING
            if cfg is None
            else RiskRuleId.RISK_INVALID_CONFIG
            if not isinstance(cfg, RiskConfig)
            else RiskRuleId.RISK_EVALUATION_ERROR
        )
        decision = _fail_closed_decision(
            cfg=cfg,
            rule_id=rule_id,
            message="risk policy evaluation failed",
            snapshot=validated.to_dict(),
        )

    try:
        audit_event = make_audit_event(component="risk_veto", action="evaluate", decision=decision)
        return decision, audit_event
    except Exception:
        decision = _fail_closed_decision(
            cfg=cfg,
            rule_id=RiskRuleId.RISK_AUDIT_ERROR,
            message="risk audit emission failed",
            snapshot=decision.snapshot,
            details={"prior_rule_ids": reason_codes(decision.reasons)},
        )
        try:
            return decision, make_audit_event(
                component="risk_veto", action="evaluate", decision=decision
            )
        except Exception:
            return decision, _fallback_audit_event(decision)
