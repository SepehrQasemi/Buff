from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from risk.types import Permission, RiskState

from .audit import DecisionRecord, DecisionWriter
from .brokers import Broker, OrderResult
from .idempotency import IdempotencyStore
from .locks import RiskLocks, evaluate_locks
from .types import ExecutionDecision, IntentSide, OrderIntent, PositionState


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        locks: RiskLocks,
        current_exposure: float | None,
        trades_today: int | None,
        data_snapshot_hash: str,
        feature_snapshot_hash: str,
        strategy_id: str,
        now_fn: Callable[[], str] = _utc_now,
    ) -> ExecutionDecision:
        if self.idempotency.seen(intent.event_id):
            decision = ExecutionDecision(
                risk_state=risk_state,
                permission=permission,
                action="duplicate",
                reason="duplicate_event",
                status="ignored",
            )
            self._write_record(intent, decision, data_snapshot_hash, feature_snapshot_hash, strategy_id, now_fn())
            return decision

        if risk_state == RiskState.RED or permission == Permission.BLOCK:
            self.idempotency.mark(intent.event_id)
            decision = ExecutionDecision(
                risk_state=risk_state,
                permission=permission,
                action="blocked",
                reason="risk_block",
                status="blocked",
            )
            self._write_record(intent, decision, data_snapshot_hash, feature_snapshot_hash, strategy_id, now_fn())
            return decision

        lock_status = evaluate_locks(
            locks,
            current_exposure=current_exposure,
            trades_today=trades_today,
            leverage=intent.leverage,
            protective_exit_required=intent.protective_exit_required,
        )
        if not lock_status.allowed:
            self.idempotency.mark(intent.event_id)
            decision = ExecutionDecision(
                risk_state=risk_state,
                permission=permission,
                action="blocked",
                reason=lock_status.reason,
                status="blocked",
            )
            self._write_record(intent, decision, data_snapshot_hash, feature_snapshot_hash, strategy_id, now_fn())
            return decision

        if intent.side == IntentSide.FLAT and self.position_state == PositionState.FLAT:
            self.idempotency.mark(intent.event_id)
            decision = ExecutionDecision(
                risk_state=risk_state,
                permission=permission,
                action="noop",
                reason="already_flat",
                status="noop",
            )
            self._write_record(intent, decision, data_snapshot_hash, feature_snapshot_hash, strategy_id, now_fn())
            return decision

        order_result = self._submit_order(intent)
        self.idempotency.mark(intent.event_id)
        self._advance_state(intent, order_result)

        decision = ExecutionDecision(
            risk_state=risk_state,
            permission=permission,
            action="placed",
            reason="ok",
            order_ids=(order_result.order_id,),
            filled_qty=order_result.filled_qty,
            status=order_result.status,
        )
        self._write_record(intent, decision, data_snapshot_hash, feature_snapshot_hash, strategy_id, now_fn())
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
        )
        self.decision_writer.append(record)
