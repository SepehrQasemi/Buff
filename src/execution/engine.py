from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import os
import json
from pathlib import Path
from typing import Callable

from risk.types import Permission, RiskState
from risk.contracts import RiskInputs
from risk.state_machine import RiskConfig as GateRiskConfig
from execution.gate import gate_execution
from risk_fundamental.integration import apply_fundamental_permission, get_default_rules_path

from .audit import DecisionRecord, DecisionWriter
from .brokers import Broker, OrderResult
from .idempotency import (
    IdempotencyStore,
    build_idempotency_record,
    make_idempotency_key,
)
from .locks import RiskLocks, evaluate_locks
from .types import ExecutionDecision, IntentSide, OrderIntent, PositionState

from control_plane.state import ControlState, SystemState
from decision_records import inputs_digest
from decision_records.schema import (
    SCHEMA_VERSION,
    ControlStatus,
    Environment,
    ExecutionStatus,
    RiskStatus,
    validate_decision_record,
)
from utils.run_id import sanitize_run_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fundamental_enabled() -> bool:
    return os.getenv("BUFF_FUNDAMENTAL_RISK", "").strip().lower() in {"1", "true", "yes", "on"}


def _fundamental_rules_path() -> str:
    return os.getenv("BUFF_FUNDAMENTAL_RULES_PATH", get_default_rules_path())


def _fundamental_snapshot_from_intent(intent: OrderIntent) -> dict:
    raw = intent.metadata.get("fundamental_snapshot")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _attach_fundamental_metadata(
    decision: ExecutionDecision, payload: dict | None, size_multiplier: float
) -> ExecutionDecision:
    if not payload:
        return decision
    return replace(decision, size_multiplier=size_multiplier, fundamental_risk=payload)


@dataclass
class ExecutionEngine:
    broker: Broker
    decision_writer: DecisionWriter
    idempotency: IdempotencyStore
    position_state: PositionState = PositionState.FLAT
    position_qty: float = 0.0

    def handle_intent(
        self,
        intent: OrderIntent,
        risk_state: RiskState,
        permission: Permission,
        risk_inputs: RiskInputs,
        risk_config: GateRiskConfig,
        locks: RiskLocks,
        current_exposure: float | None,
        trades_today: int | None,
        data_snapshot_hash: str,
        feature_snapshot_hash: str,
        strategy_id: str,
        now_fn: Callable[[], str] = _utc_now,
    ) -> ExecutionDecision:
        gate = gate_execution(risk_inputs, risk_config)
        if not gate.allowed:
            try:
                key = make_idempotency_key(intent, run_id=intent.metadata.get("run_id"))
                self.idempotency.put(
                    key,
                    build_idempotency_record(
                        status="PROCESSED",
                        order_id=None,
                        audit_ref=None,
                        decision={
                            "risk_state": gate.decision.state.value,
                            "permission": Permission.BLOCK.value,
                            "action": "blocked",
                            "reason": gate.reason or "risk_veto",
                            "status": "blocked",
                        },
                    ),
                )
            except Exception:
                return ExecutionDecision(
                    risk_state=risk_state,
                    permission=Permission.BLOCK,
                    action="blocked",
                    reason="idempotency_persist_error",
                    status="blocked",
                )
            decision = ExecutionDecision(
                risk_state=RiskState(gate.decision.state.value),
                permission=Permission.BLOCK,
                action="blocked",
                reason=gate.reason or "risk_veto",
                status="blocked",
            )
            self._write_record(
                intent, decision, data_snapshot_hash, feature_snapshot_hash, strategy_id, now_fn()
            )
            return decision

        risk_state = RiskState(gate.decision.state.value)
        permission = Permission.ALLOW if risk_state == RiskState.GREEN else Permission.RESTRICT
        fundamental_payload: dict | None = None
        applied_multiplier = 1.0
        if _fundamental_enabled():
            seed_decision = ExecutionDecision(
                risk_state=risk_state,
                permission=permission,
                action="pending",
                reason="fundamental_check",
                status="pending",
            )
            seed_decision, _fundamental = apply_fundamental_permission(
                seed_decision,
                _fundamental_snapshot_from_intent(intent),
                enabled=True,
                rules_path=_fundamental_rules_path(),
            )
            fundamental_payload = seed_decision.fundamental_risk
            applied_multiplier = seed_decision.size_multiplier
            if seed_decision.action == "blocked":
                try:
                    key = make_idempotency_key(intent, run_id=intent.metadata.get("run_id"))
                    self.idempotency.put(
                        key,
                        build_idempotency_record(
                            status="PROCESSED",
                            order_id=None,
                            audit_ref=None,
                            decision={
                                "risk_state": seed_decision.risk_state.value,
                                "permission": seed_decision.permission.value,
                                "action": seed_decision.action,
                                "reason": seed_decision.reason,
                                "status": seed_decision.status,
                            },
                        ),
                    )
                except Exception:
                    return ExecutionDecision(
                        risk_state=risk_state,
                        permission=Permission.BLOCK,
                        action="blocked",
                        reason="idempotency_persist_error",
                        status="blocked",
                    )
                self._write_record(
                    intent,
                    seed_decision,
                    data_snapshot_hash,
                    feature_snapshot_hash,
                    strategy_id,
                    now_fn(),
                )
                return seed_decision

        try:
            idempotency_key = make_idempotency_key(intent, run_id=intent.metadata.get("run_id"))
            if self.idempotency.has(idempotency_key):
                record = self.idempotency.get(idempotency_key)
                decision = ExecutionDecision(
                    risk_state=RiskState(str(record["decision"]["risk_state"])),
                    permission=Permission(str(record["decision"]["permission"])),
                    action=str(record["decision"]["action"]),
                    reason=str(record["decision"]["reason"]),
                    status=str(record["decision"]["status"]),
                    order_ids=tuple(record["decision"].get("order_ids", ())),
                    filled_qty=float(record["decision"].get("filled_qty", 0.0)),
                )
                decision = _attach_fundamental_metadata(
                    decision, fundamental_payload, applied_multiplier
                )
                self._write_record(
                    intent,
                    decision,
                    data_snapshot_hash,
                    feature_snapshot_hash,
                    strategy_id,
                    now_fn(),
                )
                return decision
        except Exception:
            return ExecutionDecision(
                risk_state=risk_state,
                permission=Permission.BLOCK,
                action="blocked",
                reason="idempotency_persist_error",
                status="blocked",
            )

        # Risk veto enforced via gate_execution only. No secondary veto here.

        lock_status = evaluate_locks(
            locks,
            current_exposure=current_exposure,
            trades_today=trades_today,
            leverage=intent.leverage,
            protective_exit_required=intent.protective_exit_required,
        )
        if not lock_status.allowed:
            decision = ExecutionDecision(
                risk_state=risk_state,
                permission=permission,
                action="blocked",
                reason=lock_status.reason,
                status="blocked",
            )
            decision = _attach_fundamental_metadata(
                decision, fundamental_payload, applied_multiplier
            )
            try:
                self.idempotency.put(
                    idempotency_key,
                    build_idempotency_record(
                        status="PROCESSED",
                        order_id=None,
                        audit_ref=None,
                        decision={
                            "risk_state": decision.risk_state.value,
                            "permission": decision.permission.value,
                            "action": decision.action,
                            "reason": decision.reason,
                            "status": decision.status,
                        },
                    ),
                )
            except Exception:
                return ExecutionDecision(
                    risk_state=risk_state,
                    permission=Permission.BLOCK,
                    action="blocked",
                    reason="idempotency_persist_error",
                    status="blocked",
                )
            self._write_record(
                intent, decision, data_snapshot_hash, feature_snapshot_hash, strategy_id, now_fn()
            )
            return decision

        if intent.side == IntentSide.FLAT and self.position_state == PositionState.FLAT:
            decision = ExecutionDecision(
                risk_state=risk_state,
                permission=permission,
                action="noop",
                reason="already_flat",
                status="noop",
            )
            decision = _attach_fundamental_metadata(
                decision, fundamental_payload, applied_multiplier
            )
            try:
                self.idempotency.put(
                    idempotency_key,
                    build_idempotency_record(
                        status="PROCESSED",
                        order_id=None,
                        audit_ref=None,
                        decision={
                            "risk_state": decision.risk_state.value,
                            "permission": decision.permission.value,
                            "action": decision.action,
                            "reason": decision.reason,
                            "status": decision.status,
                        },
                    ),
                )
            except Exception:
                return ExecutionDecision(
                    risk_state=risk_state,
                    permission=Permission.BLOCK,
                    action="blocked",
                    reason="idempotency_persist_error",
                    status="blocked",
                )
            self._write_record(
                intent, decision, data_snapshot_hash, feature_snapshot_hash, strategy_id, now_fn()
            )
            return decision

        order_intent = intent
        if applied_multiplier != 1.0:
            order_intent = replace(intent, quantity=float(intent.quantity) * applied_multiplier)

        order_result = self._submit_order(order_intent)
        self._advance_state(order_intent, order_result)

        decision = ExecutionDecision(
            risk_state=risk_state,
            permission=permission,
            action="placed",
            reason="ok",
            order_ids=(order_result.order_id,),
            filled_qty=order_result.filled_qty,
            status=order_result.status,
        )
        try:
            self.idempotency.put(
                idempotency_key,
                build_idempotency_record(
                    status="PROCESSED",
                    order_id=order_result.order_id,
                    audit_ref=None,
                    decision={
                        "risk_state": decision.risk_state.value,
                        "permission": decision.permission.value,
                        "action": decision.action,
                        "reason": decision.reason,
                        "status": decision.status,
                        "order_ids": list(decision.order_ids),
                        "filled_qty": decision.filled_qty,
                    },
                ),
            )
        except Exception:
            return ExecutionDecision(
                risk_state=risk_state,
                permission=Permission.BLOCK,
                action="blocked",
                reason="idempotency_persist_error",
                status="blocked",
            )
        decision = _attach_fundamental_metadata(decision, fundamental_payload, applied_multiplier)
        self._write_record(
            intent, decision, data_snapshot_hash, feature_snapshot_hash, strategy_id, now_fn()
        )
        return decision

    def _submit_order(self, intent: OrderIntent) -> OrderResult:
        side = "buy" if intent.side == IntentSide.LONG else "sell"
        if intent.side == IntentSide.FLAT:
            side = "sell" if self.position_qty > 0 else "buy"
        return self.broker.submit_order(intent.symbol, side, intent.quantity)

    def _advance_state(self, intent: OrderIntent, result: OrderResult) -> None:
        if intent.side in (IntentSide.LONG, IntentSide.SHORT):
            self.position_state = PositionState.OPEN
            self.position_qty = result.filled_qty
        elif intent.side == IntentSide.FLAT:
            self.position_state = PositionState.FLAT
            self.position_qty = 0.0

    def _write_record(
        self,
        intent: OrderIntent,
        decision: ExecutionDecision,
        data_snapshot_hash: str,
        feature_snapshot_hash: str,
        strategy_id: str,
        timestamp: str,
    ) -> None:
        record = DecisionRecord(
            record_version=1,
            decision_id=f"dec-{intent.event_id}",
            timestamp=timestamp,
            event_id=intent.event_id,
            intent_id=intent.intent_id,
            strategy_id=strategy_id,
            risk_state=decision.risk_state.value,
            permission=decision.permission.value,
            action=decision.action,
            reason=decision.reason,
            data_snapshot_hash=data_snapshot_hash,
            feature_snapshot_hash=feature_snapshot_hash,
            execution={
                "order_ids": list(decision.order_ids),
                "filled_qty": decision.filled_qty,
                "status": decision.status,
            },
            metadata={
                "fundamental_risk": decision.fundamental_risk,
                "applied_size_multiplier": decision.size_multiplier,
            }
            if decision.fundamental_risk is not None
            else {"applied_size_multiplier": decision.size_multiplier},
        )
        self.decision_writer.append(record)


def _utc_now_z() -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    return ts.replace("+00:00", "Z")


def _write_decision_record(path: Path, record: dict) -> None:
    validate_decision_record(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
        handle.write("\n")


def execute_paper_run(
    input_data: dict,
    features: dict,
    risk_decision: dict,
    selected_strategy: dict,
    control_state: ControlState,
) -> dict:
    if "run_id" not in input_data:
        raise ValueError("missing_run_id")
    if "timeframe" not in input_data:
        raise ValueError("missing_timeframe")
    if "risk_state" not in risk_decision:
        raise ValueError("missing_risk_state")

    run_id = sanitize_run_id(str(input_data["run_id"]))
    risk_state = str(risk_decision["risk_state"])
    if risk_state not in {RiskStatus.GREEN.value, RiskStatus.RED.value}:
        raise ValueError("invalid_risk_state")

    strategy_name = selected_strategy.get("name")
    strategy_version = selected_strategy.get("version")
    if not strategy_name or not strategy_version:
        raise ValueError("invalid_strategy")

    control_status = (
        ControlStatus.ARMED.value
        if control_state.state == SystemState.ARMED
        else ControlStatus.DISARMED.value
    )

    records_rel = Path("workspaces") / run_id / "decision_records.jsonl"
    base_dir = Path("workspaces").resolve()
    records_path = (base_dir / run_id / "decision_records.jsonl").resolve()
    if base_dir not in records_path.parents:
        raise ValueError("invalid_records_path")

    summary_payload = {
        "run_id": run_id,
        "strategy": {"name": strategy_name, "version": strategy_version},
        "risk_status": risk_state,
        "control_status": control_status,
    }
    digest = inputs_digest(summary_payload)

    execution_status = ExecutionStatus.EXECUTED.value
    reason: str | None = None
    if control_state.state != SystemState.ARMED:
        execution_status = ExecutionStatus.BLOCKED.value
        reason = "control_not_armed"
    elif risk_state == RiskStatus.RED.value:
        execution_status = ExecutionStatus.BLOCKED.value
        reason = "risk_veto"

    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "timestamp_utc": _utc_now_z(),
        "environment": Environment.PAPER.value,
        "control_status": control_status,
        "strategy": {"name": strategy_name, "version": strategy_version},
        "risk_status": risk_state,
        "execution_status": execution_status,
        "reason": reason,
        "inputs_digest": digest,
        "artifact_paths": {"decision_records": records_rel.as_posix()},
    }

    _write_decision_record(records_path, record)

    if execution_status != ExecutionStatus.EXECUTED.value:
        return {"status": "blocked", "reason": reason, "simulated": True}
    return {"status": "ok", "strategy_id": strategy_name, "simulated": True}
