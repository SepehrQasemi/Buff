"""Integration adapter for applying fundamental risk to execution decisions."""

from __future__ import annotations

from dataclasses import is_dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import FundamentalSnapshot
from .engine import FundamentalRiskDecision, FundamentalRiskEngine


def get_default_rules_path() -> str:
    return "knowledge/fundamental_risk_rules.yaml"


def _utc_epoch() -> datetime:
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return _utc_epoch()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return _utc_epoch()
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _snapshot_from_context(
    context_or_snapshot: FundamentalSnapshot | Mapping[str, Any],
) -> FundamentalSnapshot:
    if isinstance(context_or_snapshot, FundamentalSnapshot):
        return context_or_snapshot
    context = dict(context_or_snapshot or {})
    timestamp = _parse_timestamp(context.get("timestamp"))
    return FundamentalSnapshot(
        timestamp=timestamp,
        macro=dict(context.get("macro") or {}),
        onchain=dict(context.get("onchain") or {}),
        news=dict(context.get("news") or {}),
        provenance=dict(context.get("provenance") or {}),
    )


def load_latest_or_compute(
    snapshot: FundamentalSnapshot | Mapping[str, Any] | None,
    *,
    rules_path: str | None = None,
    prefer_artifact: bool = False,
    artifact_path: str = "reports/fundamental_risk_latest.json",
) -> FundamentalRiskDecision:
    if prefer_artifact:
        artifact = Path(artifact_path)
        if artifact.exists():
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            return FundamentalRiskDecision(
                timestamp=_parse_timestamp(payload.get("timestamp")),
                macro_risk_state=str(payload.get("macro_risk_state")),
                onchain_stress_level=str(payload.get("onchain_stress_level")),
                news_risk_flag=payload.get("news_risk_flag"),
                final_risk_state=str(payload.get("final_risk_state")),
                trade_permission=bool(payload.get("trade_permission")),
                size_multiplier=float(payload.get("size_multiplier", 1.0)),
                missing_inputs=list(payload.get("missing_inputs", [])),
                evidence=[],
            )

    engine = FundamentalRiskEngine()
    engine.load_rules(rules_path or get_default_rules_path())
    return engine.compute(_snapshot_from_context(snapshot or {}))


def _evidence_summary(decision: FundamentalRiskDecision) -> list[dict[str, object]]:
    summary = []
    for item in decision.evidence[:10]:
        summary.append(
            {
                "rule_id": item.rule_id,
                "domain": item.domain,
                "matched": item.matched,
                "severity": item.severity,
                "reason": item.reason,
            }
        )
    return summary


def _with_updates(decision: Any, **updates: Any) -> Any:
    if isinstance(decision, dict):
        decision.update(updates)
        return decision
    if is_dataclass(decision):
        return replace(decision, **updates)
    for key, value in updates.items():
        setattr(decision, key, value)
    return decision


def apply_fundamental_permission(
    decision: Any,
    context_or_snapshot: FundamentalSnapshot | Mapping[str, Any],
    *,
    enabled: bool,
    rules_path: str | None = None,
) -> tuple[Any, FundamentalRiskDecision | None]:
    if not enabled:
        return decision, None

    fundamental = load_latest_or_compute(context_or_snapshot, rules_path=rules_path)
    summary = _evidence_summary(fundamental)
    payload = {
        "final_risk_state": fundamental.final_risk_state,
        "trade_permission": fundamental.trade_permission,
        "size_multiplier": fundamental.size_multiplier,
        "missing_inputs": list(fundamental.missing_inputs),
        "evidence_summary": summary,
    }

    current_multiplier = getattr(decision, "size_multiplier", None)
    if current_multiplier is None:
        current_multiplier = (
            decision.get("size_multiplier", 1.0) if isinstance(decision, dict) else 1.0
        )

    if fundamental.final_risk_state == "red" or fundamental.trade_permission is False:
        decision = _with_updates(
            decision,
            action="blocked",
            reason="fundamental_risk_red",
            status="blocked",
            block_reason="fundamental_risk_red",
            size_multiplier=0.0,
            fundamental_risk=payload,
        )
        return decision, fundamental

    decision = _with_updates(
        decision,
        size_multiplier=float(current_multiplier) * float(fundamental.size_multiplier),
        fundamental_risk=payload,
    )
    return decision, fundamental
