from __future__ import annotations

from pathlib import Path

import pytest

from execution.audit import DecisionWriter
from execution.brokers import PaperBroker
from execution.engine import ExecutionEngine
from execution.idempotency import build_idempotency_record, make_idempotency_key
from execution.idempotency_sqlite import SQLiteIdempotencyStore
from execution.locks import RiskLocks
from execution.types import IntentSide, OrderIntent
from risk.contracts import RiskInputs
from risk.state_machine import RiskConfig, RiskState
from risk.types import Permission


pytestmark = pytest.mark.unit


def _locks() -> RiskLocks:
    return RiskLocks(
        max_exposure=10.0,
        max_trades_per_day=5,
        leverage_cap=3.0,
        kill_switch=False,
        mandatory_protective_exit=True,
    )


def _risk_inputs() -> RiskInputs:
    return RiskInputs(
        symbol="BTCUSDT",
        timeframe="1h",
        as_of="2024-01-01T00:00:00+00:00",
        atr_pct=0.005,
        realized_vol=0.005,
        missing_fraction=0.0,
        timestamps_valid=True,
        latest_metrics_valid=True,
        invalid_index=False,
        invalid_close=False,
    )


def _risk_config() -> RiskConfig:
    return RiskConfig(
        missing_red=0.2, atr_yellow=0.02, atr_red=0.05, rvol_yellow=0.02, rvol_red=0.05
    )


def _intent(event_id: str, qty: float = 1.0) -> OrderIntent:
    return OrderIntent(
        event_id=event_id,
        intent_id=f"intent-{event_id}",
        symbol="BTCUSDT",
        timeframe="1h",
        side=IntentSide.LONG,
        quantity=qty,
        leverage=1.0,
        protective_exit_required=True,
    )


def _engine(tmp_path: Path, broker: PaperBroker, db_path: Path) -> ExecutionEngine:
    return ExecutionEngine(
        broker=broker,
        decision_writer=DecisionWriter(tmp_path / "decision.jsonl"),
        idempotency=SQLiteIdempotencyStore(db_path),
    )


def test_persistent_dedupe_across_restarts(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine_a = _engine(tmp_path, broker, db_path)
    engine_b = _engine(tmp_path, broker, db_path)
    intent = _intent("evt-1")

    engine_a.handle_intent(
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
    engine_b.handle_intent(
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


def test_unique_constraint_preserves_first_record(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    store = SQLiteIdempotencyStore(db_path)
    key = "idem-key"
    record_one = build_idempotency_record(
        status="PROCESSED",
        order_id="order-1",
        audit_ref="audit-1",
        decision={"action": "placed"},
        timestamp_utc="2026-01-01T00:00:00Z",
    )
    record_two = build_idempotency_record(
        status="PROCESSED",
        order_id="order-2",
        audit_ref="audit-2",
        decision={"action": "placed"},
        timestamp_utc="2026-01-01T00:00:00Z",
    )

    store.put(key, record_one)
    store.put(key, record_two)
    stored = store.get(key)

    assert stored["order_id"] == "order-1"
    assert stored["audit_ref"] == "audit-1"


def test_db_failure_blocks_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine = _engine(tmp_path, broker, db_path)

    def _boom() -> None:
        raise RuntimeError("db_down")

    monkeypatch.setattr(engine.idempotency, "_connect", _boom)
    decision = engine.handle_intent(
        intent=_intent("evt-2"),
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

    assert decision.action == "blocked"
    assert decision.reason == "idempotency_persist_error"
    assert broker.submitted == []


def test_different_intents_generate_distinct_keys(tmp_path: Path) -> None:
    intent_a = _intent("evt-1", qty=1.0)
    intent_b = _intent("evt-2", qty=2.0)

    key_a = make_idempotency_key(intent_a)
    key_b = make_idempotency_key(intent_b)

    assert key_a != key_b
