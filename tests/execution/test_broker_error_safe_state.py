from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from control_plane.state import ControlState, SystemState
from decision_records.schema import validate_decision_record
from execution.audit import DecisionWriter
from execution.brokers import BrokerError, OrderResult, PaperBroker
from execution.engine import ExecutionEngine, execute_paper_run
from execution.idempotency import IdempotencyStore
from execution.locks import RiskLocks
from execution.trade_log import TRADE_SCHEMA
from execution.types import IntentSide, OrderIntent
from risk.contracts import RiskInputs
from risk.contracts import RiskConfig as GateRiskConfig
from risk.contracts import Permission, RiskState


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
        atr_pct=0.01,
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


def test_execute_paper_run_broker_error_records_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    broker = PaperBroker(fail_on_submit=True, error=BrokerError("boom"))
    out = execute_paper_run(
        input_data={"run_id": "run1", "timeframe": "1m"},
        features={},
        risk_decision={"risk_state": "GREEN"},
        selected_strategy={"name": "demo", "version": "1.0.0"},
        control_state=ControlState(state=SystemState.ARMED),
        broker=broker,
    )
    assert out["status"] == "error"
    record = json.loads(Path("workspaces/run1/decision_records.jsonl").read_text())
    validate_decision_record(record)
    assert record["execution_status"] == "ERROR"
    assert "broker_error" in record["reason"]
    trades_path = Path("workspaces/run1/trades.parquet")
    assert trades_path.exists()
    df = pd.read_parquet(trades_path, engine="pyarrow")
    assert df.empty
    assert list(df.columns) == list(TRADE_SCHEMA.names)
    assert broker.submitted == []


def test_engine_safe_state_blocks_followup(tmp_path: Path) -> None:
    class FlakyBroker:
        def __init__(self) -> None:
            self.calls = 0
            self.submitted: list[OrderResult] = []

        def submit_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
            self.calls += 1
            if self.calls == 1:
                raise BrokerError("boom")
            result = OrderResult(order_id="paper-1", filled_qty=quantity, status="filled")
            self.submitted.append(result)
            return result

        def cancel_order(self, order_id: str) -> None:
            return None

    broker = FlakyBroker()
    engine = ExecutionEngine(
        broker=broker,
        decision_writer=DecisionWriter(tmp_path / "decision.jsonl"),
        idempotency=IdempotencyStore(),
    )
    decision = engine.handle_intent(
        intent=_intent("evt-1"),
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
    assert decision.status == "error"
    assert engine.safe_state is True
    followup = engine.handle_intent(
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
    assert followup.reason == "broker_error_safe_state"
    assert broker.calls == 1


def test_broker_error_leaves_idempotency_inflight(tmp_path: Path) -> None:
    broker = PaperBroker(fail_on_submit=True, error=BrokerError("boom"))
    idempotency = IdempotencyStore()
    engine = ExecutionEngine(
        broker=broker,
        decision_writer=DecisionWriter(tmp_path / "decision.jsonl"),
        idempotency=idempotency,
    )
    intent = _intent("evt-3")
    decision = engine.handle_intent(
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
    assert decision.status == "error"
    key = idempotency.records.keys()
    assert len(key) == 1
    idem_key = next(iter(key))
    assert idempotency.get_record(idem_key)["status"] == "INFLIGHT", (
        "See EXECUTION_SAFETY.md#idempotency-inflight-broker-error-fail-closed"
    )

    # Manual intervention required: idempotency is not finalized after broker error.
    followup = engine.handle_intent(
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
    assert followup.reason == "broker_error_safe_state"
