from __future__ import annotations

from pathlib import Path

import pytest
from datetime import datetime, timezone

from execution.audit import DecisionWriter
from execution.brokers import PaperBroker
from execution.engine import ExecutionEngine
from execution.idempotency import build_inflight_record, make_idempotency_key
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


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_utc(self) -> datetime:
        return self._now


def test_finalize_failure_keeps_inflight_and_blocks_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine = _engine(tmp_path, broker, db_path)
    intent = _intent("evt-1")

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("finalize_failed")

    monkeypatch.setattr(engine.idempotency, "finalize_processed", _boom)
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))

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
        clock=clock,
        inflight_ttl_seconds=600,
    )

    assert len(broker.submitted) == 1
    assert decision.action == "error"
    assert decision.reason == "idempotency_finalize_error"

    decision_retry = engine.handle_intent(
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
        clock=clock,
        inflight_ttl_seconds=600,
    )

    assert len(broker.submitted) == 1
    assert decision_retry.action == "blocked"
    assert decision_retry.reason == "idempotency_inflight"


def test_processed_dedupes_without_resubmit(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine = _engine(tmp_path, broker, db_path)
    intent = _intent("evt-2")
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))

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
        clock=clock,
        inflight_ttl_seconds=600,
    )
    decision_retry = engine.handle_intent(
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
        clock=clock,
        inflight_ttl_seconds=600,
    )

    assert len(broker.submitted) == 1
    assert decision.action == "placed"
    assert decision_retry.action == "placed"


def test_inflight_record_blocks_second_attempt(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine = _engine(tmp_path, broker, db_path)
    intent = _intent("evt-3")

    key = make_idempotency_key(intent)
    store = SQLiteIdempotencyStore(db_path)
    store.reserve_inflight(
        key,
        build_inflight_record(
            first_seen_utc="2026-01-01T00:00:00Z",
            reserved_at_utc="2026-01-01T00:00:00Z",
            reservation_token=1,
        ),
    )
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))

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
        clock=clock,
        inflight_ttl_seconds=600,
    )

    assert broker.submitted == []
    assert decision.action == "blocked"
    assert decision.reason == "idempotency_inflight"


def test_different_intents_submit_twice(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine = _engine(tmp_path, broker, db_path)
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))

    engine.handle_intent(
        intent=_intent("evt-4", qty=1.0),
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
        clock=clock,
        inflight_ttl_seconds=600,
    )
    engine.handle_intent(
        intent=_intent("evt-5", qty=2.0),
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
        clock=clock,
        inflight_ttl_seconds=600,
    )

    assert len(broker.submitted) == 2


def test_reserve_failure_blocks_before_submit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine = _engine(tmp_path, broker, db_path)

    def _boom(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("store_down")

    monkeypatch.setattr(engine.idempotency, "reserve_inflight", _boom)

    decision = engine.handle_intent(
        intent=_intent("evt-6"),
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
        clock=FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc)),
        inflight_ttl_seconds=600,
    )

    assert broker.submitted == []
    assert decision.action == "blocked"
    assert decision.reason == "idempotency_persist_error"


def test_invalid_decision_blocks_fail_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine = _engine(tmp_path, broker, db_path)
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))

    decision = engine.handle_intent(
        intent=_intent("evt-7"),
        risk_state=RiskState.GREEN,
        permission=Permission.ALLOW,
        risk_inputs=_risk_inputs(),
        risk_config=_risk_config(),
        locks=_locks(),
        current_exposure=0.0,
        trades_today=0,
        data_snapshot_hash="data",
        feature_snapshot_hash="features",
        strategy_id="",
        clock=clock,
        inflight_ttl_seconds=600,
    )

    assert broker.submitted == []
    assert decision.action == "blocked"
    assert "invalid_decision_schema" in decision.reason
