from __future__ import annotations

from pathlib import Path

import pytest

from execution.audit import DecisionWriter
from execution.brokers import PaperBroker
from execution.engine import ExecutionEngine
from execution.idempotency import IdempotencyStore
from execution.locks import RiskLocks
from execution.types import IntentSide, OrderIntent
from risk.contracts import RiskInputs
from risk.contracts import RiskConfig, RiskState
from risk.contracts import Permission


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


def _engine(tmp_path: Path) -> tuple[ExecutionEngine, PaperBroker]:
    broker = PaperBroker()
    engine = ExecutionEngine(
        broker=broker,
        decision_writer=DecisionWriter(tmp_path / "decision.jsonl"),
        idempotency=IdempotencyStore(),
    )
    return engine, broker


def test_dedup_same_intent(tmp_path: Path) -> None:
    engine, broker = _engine(tmp_path)
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


def test_dedup_diff_intent_qty(tmp_path: Path) -> None:
    engine, broker = _engine(tmp_path)
    engine.handle_intent(
        intent=_intent("evt-1", qty=1.0),
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
        intent=_intent("evt-2", qty=2.0),
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
    assert len(broker.submitted) == 2


def test_store_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, broker = _engine(tmp_path)

    def _boom(_key: str, _record: dict) -> bool:
        raise RuntimeError("store_down")

    monkeypatch.setattr(engine.idempotency, "reserve_inflight", _boom)
    decision = engine.handle_intent(
        intent=_intent("evt-3"),
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
