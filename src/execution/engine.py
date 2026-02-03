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
from .brokers import Broker, OrderResult, PaperBroker
from .idempotency import (
    IdempotencyStore,
    build_idempotency_record,
    build_inflight_record,
    make_idempotency_key,
)
from .locks import RiskLocks, evaluate_locks
from .types import ExecutionDecision, IntentSide, OrderIntent, PositionState
from .clock import Clock, SystemClock, format_utc, parse_utc
from .decision_contract import DecisionValidationError, build_decision_payload
from .trade_log import write_trades_parquet

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


def _inflight_ttl_seconds() -> int | None:
    raw = os.getenv("BUFF_IDEMPOTENCY_INFLIGHT_TTL_SECONDS", "600").strip()
    try:
        ttl = int(raw)
    except ValueError:
        return None
    return ttl if ttl >= 0 else None


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
    safe_state: bool = False

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
        clock: Clock | None = None,
        inflight_ttl_seconds: int | None = None,
    ) -> ExecutionDecision:
        ttl = inflight_ttl_seconds if inflight_ttl_seconds is not None else _inflight_ttl_seconds()
        if ttl is None:
            return ExecutionDecision(
                risk_state=risk_state,
                permission=Permission.BLOCK,
                action="blocked",
                reason="idempotency_config_error",
                status="blocked",
            )
        clock = clock or SystemClock()
        try:
            now_dt = clock.now_utc()
        except Exception:
            return ExecutionDecision(
                risk_state=risk_state,
                permission=Permission.BLOCK,
                action="blocked",
                reason="idempotency_clock_error",
                status="blocked",
            )
        now_str = format_utc(now_dt)
        if self.safe_state:
            decision = ExecutionDecision(
                risk_state=risk_state,
                permission=Permission.BLOCK,
                action="blocked",
                reason="broker_error_safe_state",
                status="blocked",
            )
            self._write_record(
                intent,
                decision,
                data_snapshot_hash,
                feature_snapshot_hash,
                strategy_id,
                now_str,
            )
            return decision

        idempotency_key = make_idempotency_key(intent, run_id=intent.metadata.get("run_id"))
        first_seen_utc = now_str
        try:
            reserved = self.idempotency.reserve_inflight(
                idempotency_key,
                build_inflight_record(
                    first_seen_utc=first_seen_utc,
                    reserved_at_utc=first_seen_utc,
                    reservation_token=1,
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

        if not reserved:
            try:
                record = self.idempotency.get_record(idempotency_key)
            except Exception:
                return ExecutionDecision(
                    risk_state=risk_state,
                    permission=Permission.BLOCK,
                    action="blocked",
                    reason="idempotency_persist_error",
                    status="blocked",
                )
            status = str(record.get("status", ""))
            if status == "PROCESSED":
                result = record.get("result") or record.get("decision") or {}
                decision = ExecutionDecision(
                    risk_state=RiskState(str(result.get("risk_state", risk_state.value))),
                    permission=Permission(str(result.get("permission", permission.value))),
                    action=str(result.get("action", "blocked")),
                    reason=str(result.get("reason", "idempotency_deduped")),
                    status=str(result.get("status", "blocked")),
                    order_ids=tuple(result.get("order_ids", ())),
                    filled_qty=float(result.get("filled_qty", 0.0)),
                )
                self._write_record(
                    intent,
                    decision,
                    data_snapshot_hash,
                    feature_snapshot_hash,
                    strategy_id,
                    now_str,
                )
                return decision
            if status == "INFLIGHT":
                reserved_at_utc = record.get("reserved_at_utc")
                token = record.get("reservation_token")
                if not isinstance(reserved_at_utc, str) or token is None:
                    return ExecutionDecision(
                        risk_state=risk_state,
                        permission=Permission.BLOCK,
                        action="blocked",
                        reason="idempotency_inflight_unknown",
                        status="blocked",
                    )
                try:
                    reserved_at = parse_utc(reserved_at_utc)
                except Exception:
                    return ExecutionDecision(
                        risk_state=risk_state,
                        permission=Permission.BLOCK,
                        action="blocked",
                        reason="idempotency_clock_error",
                        status="blocked",
                    )
                age_seconds = (now_dt - reserved_at).total_seconds()
                if age_seconds <= ttl:
                    return ExecutionDecision(
                        risk_state=risk_state,
                        permission=Permission.BLOCK,
                        action="blocked",
                        reason="idempotency_inflight",
                        status="blocked",
                    )
                next_reserved_at = now_str
                first_seen_utc = record.get("first_seen_utc") or reserved_at_utc
                new_record = build_inflight_record(
                    first_seen_utc=str(first_seen_utc),
                    reserved_at_utc=next_reserved_at,
                    reservation_token=int(token) + 1,
                )
                try:
                    recovered = self.idempotency.try_recover_inflight(
                        idempotency_key,
                        old_reserved_at_utc=reserved_at_utc,
                        new_record=new_record,
                    )
                except Exception:
                    return ExecutionDecision(
                        risk_state=risk_state,
                        permission=Permission.BLOCK,
                        action="blocked",
                        reason="idempotency_persist_error",
                        status="blocked",
                    )
                if not recovered:
                    try:
                        record = self.idempotency.get_record(idempotency_key)
                    except Exception:
                        return ExecutionDecision(
                            risk_state=risk_state,
                            permission=Permission.BLOCK,
                            action="blocked",
                            reason="idempotency_persist_error",
                            status="blocked",
                        )
                    status = str(record.get("status", ""))
                    if status == "PROCESSED":
                        result = record.get("result") or record.get("decision") or {}
                        decision = ExecutionDecision(
                            risk_state=RiskState(str(result.get("risk_state", risk_state.value))),
                            permission=Permission(str(result.get("permission", permission.value))),
                            action=str(result.get("action", "blocked")),
                            reason=str(result.get("reason", "idempotency_deduped")),
                            status=str(result.get("status", "blocked")),
                            order_ids=tuple(result.get("order_ids", ())),
                            filled_qty=float(result.get("filled_qty", 0.0)),
                        )
                        self._write_record(
                            intent,
                            decision,
                            data_snapshot_hash,
                            feature_snapshot_hash,
                            strategy_id,
                            now_str,
                        )
                        return decision
                    return ExecutionDecision(
                        risk_state=risk_state,
                        permission=Permission.BLOCK,
                        action="blocked",
                        reason="idempotency_inflight",
                        status="blocked",
                    )
                first_seen_utc = str(first_seen_utc)
            else:
                return ExecutionDecision(
                    risk_state=risk_state,
                    permission=Permission.BLOCK,
                    action="blocked",
                    reason="idempotency_unknown",
                    status="blocked",
                )

        gate = gate_execution(risk_inputs, risk_config)
        if not gate.allowed:
            decision = ExecutionDecision(
                risk_state=RiskState(gate.decision.state.value),
                permission=Permission.BLOCK,
                action="blocked",
                reason=gate.reason or "risk_veto",
                status="blocked",
            )
            timestamp = now_str
            decision = self._finalize_and_record(
                idempotency_key=idempotency_key,
                decision=decision,
                intent=intent,
                data_snapshot_hash=data_snapshot_hash,
                feature_snapshot_hash=feature_snapshot_hash,
                strategy_id=strategy_id,
                timestamp=timestamp,
                first_seen_utc=str(first_seen_utc),
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
                timestamp = now_str
                seed_decision = self._finalize_and_record(
                    idempotency_key=idempotency_key,
                    decision=seed_decision,
                    intent=intent,
                    data_snapshot_hash=data_snapshot_hash,
                    feature_snapshot_hash=feature_snapshot_hash,
                    strategy_id=strategy_id,
                    timestamp=timestamp,
                    first_seen_utc=str(first_seen_utc),
                )
                return seed_decision

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
            timestamp = now_str
            decision = self._finalize_and_record(
                idempotency_key=idempotency_key,
                decision=decision,
                intent=intent,
                data_snapshot_hash=data_snapshot_hash,
                feature_snapshot_hash=feature_snapshot_hash,
                strategy_id=strategy_id,
                timestamp=timestamp,
                first_seen_utc=str(first_seen_utc),
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
            timestamp = now_str
            decision = self._finalize_and_record(
                idempotency_key=idempotency_key,
                decision=decision,
                intent=intent,
                data_snapshot_hash=data_snapshot_hash,
                feature_snapshot_hash=feature_snapshot_hash,
                strategy_id=strategy_id,
                timestamp=timestamp,
                first_seen_utc=str(first_seen_utc),
            )
            return decision

        order_intent = intent
        if applied_multiplier != 1.0:
            order_intent = replace(intent, quantity=float(intent.quantity) * applied_multiplier)

        try:
            side = "buy" if order_intent.side == IntentSide.LONG else "sell"
            if order_intent.side == IntentSide.FLAT:
                side = "sell" if self.position_qty > 0 else "buy"
            strategy_version = order_intent.metadata.get("strategy_version", 1)
            inputs_payload = {
                "strategy_id": strategy_id,
                "strategy_version": strategy_version,
                "step_id": intent.event_id,
                "data_snapshot_hash": data_snapshot_hash,
                "feature_snapshot_hash": feature_snapshot_hash,
                "risk_state": risk_state.value,
                "permission": permission.value,
                "current_exposure": current_exposure,
                "trades_today": trades_today,
            }
            build_decision_payload(
                action="allow",
                reason="ok",
                strategy_id=strategy_id,
                strategy_version=int(strategy_version),
                step_id=intent.event_id,
                inputs_payload=inputs_payload,
                orders=[
                    {
                        "symbol": order_intent.symbol,
                        "side": side,
                        "qty": float(order_intent.quantity),
                        "order_type": "market",
                        "limit_price": None,
                    }
                ],
            )
        except (ValueError, TypeError, DecisionValidationError) as exc:
            return ExecutionDecision(
                risk_state=risk_state,
                permission=Permission.BLOCK,
                action="blocked",
                reason=f"invalid_decision_schema:{exc}",
                status="blocked",
            )

        try:
            order_result = self._submit_order(order_intent)
        except Exception as exc:
            self.safe_state = True
            decision = ExecutionDecision(
                risk_state=risk_state,
                permission=Permission.BLOCK,
                action="error",
                reason=f"broker_error:{type(exc).__name__}",
                status="error",
            )
            timestamp = now_str
            # Fail-closed on broker error: do not mark idempotency as processed.
            self._write_record(
                intent,
                decision,
                data_snapshot_hash,
                feature_snapshot_hash,
                strategy_id,
                timestamp,
            )
            return decision
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
        decision = _attach_fundamental_metadata(decision, fundamental_payload, applied_multiplier)
        timestamp = now_str
        decision = self._finalize_and_record(
            idempotency_key=idempotency_key,
            decision=decision,
            intent=intent,
            data_snapshot_hash=data_snapshot_hash,
            feature_snapshot_hash=feature_snapshot_hash,
            strategy_id=strategy_id,
            timestamp=timestamp,
            first_seen_utc=str(first_seen_utc),
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

    def _finalize_and_record(
        self,
        *,
        idempotency_key: str,
        decision: ExecutionDecision,
        intent: OrderIntent,
        data_snapshot_hash: str,
        feature_snapshot_hash: str,
        strategy_id: str,
        timestamp: str,
        first_seen_utc: str,
    ) -> ExecutionDecision:
        payload = {
            "risk_state": decision.risk_state.value,
            "permission": decision.permission.value,
            "action": decision.action,
            "reason": decision.reason,
            "status": decision.status,
        }
        order_id = None
        if decision.order_ids:
            order_id = decision.order_ids[0]
            payload["order_ids"] = list(decision.order_ids)
            payload["filled_qty"] = decision.filled_qty
        record_decision = decision
        finalize_error = False
        try:
            self.idempotency.finalize_processed(
                idempotency_key,
                build_idempotency_record(
                    status="PROCESSED",
                    order_id=order_id,
                    audit_ref=None,
                    decision=payload,
                    timestamp_utc=timestamp,
                    first_seen_utc=first_seen_utc,
                ),
            )
        except Exception:
            finalize_error = True
            record_decision = ExecutionDecision(
                risk_state=decision.risk_state,
                permission=Permission.BLOCK,
                action="error",
                reason="idempotency_finalize_error",
                status="error",
            )
        finally:
            self._write_record(
                intent,
                record_decision,
                data_snapshot_hash,
                feature_snapshot_hash,
                strategy_id,
                timestamp,
            )
        if finalize_error:
            return record_decision
        return decision


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
    broker: Broker | None = None,
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
    trades_path = (base_dir / run_id / "trades.parquet").resolve()
    if base_dir not in trades_path.parents:
        raise ValueError("invalid_trades_path")

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
        if control_state.reason and "kill_switch" in control_state.reason:
            reason = "kill_switch"
        else:
            reason = "control_not_armed"
    elif risk_state == RiskStatus.RED.value:
        execution_status = ExecutionStatus.BLOCKED.value
        reason = "risk_veto"

    order_rows: list[dict[str, object]] = []
    broker = broker or PaperBroker()
    symbol = str(input_data.get("symbol") or "")
    side = str(input_data.get("side") or "buy")
    quantity_raw = input_data.get("quantity")
    try:
        quantity = float(quantity_raw) if quantity_raw is not None else 0.0
    except (TypeError, ValueError):
        quantity = 0.0

    timestamp_utc = _utc_now_z()
    if execution_status == ExecutionStatus.EXECUTED.value:
        try:
            result = broker.submit_order(symbol, side, quantity)
            order_rows.append(
                {
                    "run_id": run_id,
                    "ts_utc": timestamp_utc,
                    "order_id": result.order_id,
                    "symbol": symbol,
                    "side": side,
                    "qty": result.filled_qty,
                    "status": result.status,
                    "reason": "",
                    "execution_status": execution_status,
                }
            )
        except Exception as exc:
            execution_status = ExecutionStatus.ERROR.value
            reason = f"broker_error:{type(exc).__name__}"

    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
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
    write_trades_parquet(trades_path, order_rows)

    if execution_status == ExecutionStatus.ERROR.value:
        return {"status": "error", "reason": reason, "simulated": True}
    if execution_status == ExecutionStatus.BLOCKED.value:
        return {"status": "blocked", "reason": reason, "simulated": True}
    return {"status": "executed", "strategy_id": strategy_name, "simulated": True}
