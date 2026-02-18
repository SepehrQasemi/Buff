"""Audit event schema and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import uuid
from typing import Any

from risk.contracts import RiskDecision, reason_codes, reason_payloads


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    ts_utc: str
    component: str
    action: str
    inputs_hash: str
    decision: str
    reasons: list[str]
    snapshot: dict[str, Any]
    reason_details: list[dict[str, Any]] = field(default_factory=list)
    config_version: str = "v1"
    inputs_digest: str = ""


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now_z() -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return ts.replace("+00:00", "Z")


def make_audit_event(component: str, action: str, decision: RiskDecision) -> AuditEvent:
    payload = canonical_json(decision.snapshot)
    return AuditEvent(
        event_id=str(uuid.uuid4()),
        ts_utc=_utc_now_z(),
        component=component,
        action=action,
        inputs_hash=sha256_hex(payload),
        decision=decision.state.value,
        reasons=reason_codes(decision.reasons),
        reason_details=reason_payloads(decision.reasons),
        snapshot=decision.snapshot,
        config_version=decision.config_version,
        inputs_digest=decision.inputs_digest,
    )
