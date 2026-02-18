from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from execution.audit import DecisionWriter
from execution.brokers import PaperBroker
from execution.engine import ExecutionEngine
from execution.idempotency_sqlite import SQLiteIdempotencyStore, default_idempotency_db_path
from execution.locks import RiskLocks
from execution.types import ExecutionDecision, OrderIntent
from risk.contracts import RiskInputs
from risk.contracts import RiskConfig as GateRiskConfig
from risk.contracts import Permission, RiskState
from strategies.registry import StrategyRegistry


@dataclass
class ControlPlaneState:
    armed: bool = False
    kill_switch: bool = False
    approved_strategies: set[str] = field(default_factory=set)


class ControlPlane:
    """Arms execution and enforces approvals."""

    def __init__(self, state: ControlPlaneState | None = None) -> None:
        self.state = state or ControlPlaneState()

    def status(self) -> ControlPlaneState:
        return self.state

    def arm_live(self, strategy_id: str) -> None:
        if strategy_id not in self.state.approved_strategies:
            raise ValueError("strategy_not_approved")
        self.state.armed = True

    def disarm_live(self) -> None:
        self.state.armed = False

    def kill_switch(self) -> None:
        self.state.kill_switch = True

    def clear_kill_switch(self) -> None:
        self.state.kill_switch = False

    def approve_strategy(self, registry: StrategyRegistry, strategy_id: str) -> None:
        if not registry.is_approved(strategy_id):
            raise ValueError("strategy_not_approved")
        self.state.approved_strategies.add(strategy_id)

    def run_paper(
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
        decision_path: Path,
    ) -> ExecutionDecision:
        if not self.state.armed:
            return ExecutionDecision(
                risk_state=risk_state,
                permission=permission,
                action="blocked",
                reason="not_armed",
                status="blocked",
            )
        if strategy_id not in self.state.approved_strategies:
            return ExecutionDecision(
                risk_state=risk_state,
                permission=permission,
                action="blocked",
                reason="strategy_not_approved",
                status="blocked",
            )
        if self.state.kill_switch:
            return ExecutionDecision(
                risk_state=risk_state,
                permission=permission,
                action="blocked",
                reason="kill_switch",
                status="blocked",
            )
        engine = ExecutionEngine(
            broker=PaperBroker(),
            decision_writer=DecisionWriter(decision_path),
            idempotency=SQLiteIdempotencyStore(default_idempotency_db_path()),
        )
        return engine.handle_intent(
            intent=intent,
            risk_state=risk_state,
            permission=permission,
            risk_inputs=risk_inputs,
            risk_config=risk_config,
            locks=locks,
            current_exposure=current_exposure,
            trades_today=trades_today,
            data_snapshot_hash=data_snapshot_hash,
            feature_snapshot_hash=feature_snapshot_hash,
            strategy_id=strategy_id,
        )
