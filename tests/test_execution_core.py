from __future__ import annotations

from pathlib import Path

from execution.audit import DecisionWriter
from execution.brokers import PaperBroker
from execution.engine import ExecutionEngine
from execution.idempotency import IdempotencyStore
from execution.locks import RiskLocks
from execution.types import IntentSide, OrderIntent
from risk.contracts import RiskInputs
from risk.state_machine import RiskConfig as GateRiskConfig
from risk.types import Permission, RiskState


def _intent(event_id: str) -> OrderIntent:
    return OrderIntent(
        event_id=event_id,
        intent_id=f"intent-{event_id}",
        symbol="BTCUSDT",
        timeframe="1h",
        side=IntentSide.LONG,
        quantity=1.0,
        leverage=1.0,
        protective_exit_required=True,
    )


def _locks(kill_switch: bool = False) -> RiskLocks:
    return RiskLocks(
        max_exposure=10.0,
        max_trades_per_day=5,
        leverage_cap=3.0,
        kill_switch=kill_switch,
        mandatory_protective_exit=True,
    )


def _risk_inputs(atr_pct: float | None = 0.01) -> RiskInputs:
    return RiskInputs(
        symbol="BTCUSDT",
        timeframe="1h",
        as_of="2024-01-01T00:00:00+00:00",
        atr_pct=atr_pct,
        realized_vol=0.01,
        missing_fraction=0.0,
        timestamps_valid=True,
        latest_metrics_valid=True,
        invalid_index=False,
        invalid_close=False,
    )


def _risk_config() -> GateRiskConfig:
    return GateRiskConfig(
        missing_red=0.2, atr_yellow=0.02, atr_red=0.05, rvol_yellow=0.02, rvol_red=0.05
    )


def test_duplicate_event_idempotency(tmp_path: Path) -> None:
    broker = PaperBroker()
    engine = ExecutionEngine(
        broker=broker,
        decision_writer=DecisionWriter(tmp_path / "decision.jsonl"),
        idempotency=IdempotencyStore(),
    )
    intent = _intent("evt-1")
    engine.handle_intent(
        intent=intent,
        risk_state=RiskState.GREEN,
        permission=Permission.ALLOW,
        risk_inputs=_risk_inputs(),
        risk_config=_risk_config(),
        locks=_locks(),
        current_exposure=0.0,
        trades_today=0,
        data_snapshot_hash="data",
        feature_snapshot_hash="features",
        strategy_id="strat-1",
    )
    engine.handle_intent(
        intent=intent,
        risk_state=RiskState.GREEN,
        permission=Permission.ALLOW,
        risk_inputs=_risk_inputs(),
        risk_config=_risk_config(),
        locks=_locks(),
        current_exposure=0.0,
        trades_today=0,
        data_snapshot_hash="data",
        feature_snapshot_hash="features",
        strategy_id="strat-1",
    )
    assert len(broker.submitted) == 1


def test_risk_red_blocks_execution(tmp_path: Path) -> None:
    broker = PaperBroker()
    engine = ExecutionEngine(
        broker=broker,
        decision_writer=DecisionWriter(tmp_path / "decision.jsonl"),
        idempotency=IdempotencyStore(),
    )
    decision = engine.handle_intent(
        intent=_intent("evt-2"),
        risk_state=RiskState.RED,
        permission=Permission.BLOCK,
        risk_inputs=_risk_inputs(atr_pct=0.1),
        risk_config=_risk_config(),
        locks=_locks(),
        current_exposure=0.0,
        trades_today=0,
        data_snapshot_hash="data",
        feature_snapshot_hash="features",
        strategy_id="strat-1",
    )
    assert decision.action == "blocked"
    assert len(broker.submitted) == 0


def test_kill_switch_blocks_execution(tmp_path: Path) -> None:
    broker = PaperBroker()
    engine = ExecutionEngine(
        broker=broker,
        decision_writer=DecisionWriter(tmp_path / "decision.jsonl"),
        idempotency=IdempotencyStore(),
    )
    decision = engine.handle_intent(
        intent=_intent("evt-3"),
        risk_state=RiskState.GREEN,
        permission=Permission.ALLOW,
        risk_inputs=_risk_inputs(),
        risk_config=_risk_config(),
        locks=_locks(kill_switch=True),
        current_exposure=0.0,
        trades_today=0,
        data_snapshot_hash="data",
        feature_snapshot_hash="features",
        strategy_id="strat-1",
    )
    assert decision.action == "blocked"
    assert decision.reason == "kill_switch"
    assert len(broker.submitted) == 0
