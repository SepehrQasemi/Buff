from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from execution.audit import DecisionWriter
from execution.brokers import PaperBroker
from execution.engine import ExecutionEngine
from execution.idempotency import build_inflight_record, make_idempotency_key
from execution.idempotency_sqlite import SQLiteIdempotencyStore
from execution.locks import RiskLocks
from execution.types import IntentSide, OrderIntent
from risk.contracts import RiskInputs
from risk.contracts import RiskConfig, RiskState
from risk.contracts import Permission


pytestmark = pytest.mark.unit


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_utc(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now = self._now + delta


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


def test_non_expired_inflight_blocks(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine = _engine(tmp_path, broker, db_path)
    intent = _intent("evt-1")
    store = SQLiteIdempotencyStore(db_path)

    reserved_at = "2026-01-01T00:00:00Z"
    store.reserve_inflight(
        make_idempotency_key(intent),
        build_inflight_record(
            first_seen_utc=reserved_at,
            reserved_at_utc=reserved_at,
            reservation_token=1,
        ),
    )
    clock = FakeClock(datetime(2026, 1, 1, 0, 9, 59, tzinfo=timezone.utc))

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


def test_expired_inflight_recovers_and_submits(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine = _engine(tmp_path, broker, db_path)
    intent = _intent("evt-2")
    store = SQLiteIdempotencyStore(db_path)

    reserved_at = "2026-01-01T00:00:00Z"
    store.reserve_inflight(
        make_idempotency_key(intent),
        build_inflight_record(
            first_seen_utc=reserved_at,
            reserved_at_utc=reserved_at,
            reservation_token=1,
        ),
    )
    clock = FakeClock(datetime(2026, 1, 1, 0, 10, 1, tzinfo=timezone.utc))

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
    assert decision.action == "placed"


def test_recovery_race_only_one_submits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine = _engine(tmp_path, broker, db_path)
    intent = _intent("evt-3")
    store = SQLiteIdempotencyStore(db_path)

    reserved_at = "2026-01-01T00:00:00Z"
    store.reserve_inflight(
        make_idempotency_key(intent),
        build_inflight_record(
            first_seen_utc=reserved_at,
            reserved_at_utc=reserved_at,
            reservation_token=1,
        ),
    )
    clock = FakeClock(datetime(2026, 1, 1, 0, 10, 1, tzinfo=timezone.utc))

    calls = {"count": 0}

    def _recover_once(*_args: object, **_kwargs: object) -> bool:
        calls["count"] += 1
        return calls["count"] == 1

    monkeypatch.setattr(engine.idempotency, "try_recover_inflight", _recover_once)

    decision_a = engine.handle_intent(
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
    decision_b = engine.handle_intent(
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
    assert decision_a.action in {"placed", "blocked"}
    assert decision_b.action in {"placed", "blocked"}


def test_clock_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "idem.sqlite"
    broker = PaperBroker()
    engine = _engine(tmp_path, broker, db_path)
    intent = _intent("evt-4")
    store = SQLiteIdempotencyStore(db_path)

    reserved_at = "2026-01-01T00:00:00Z"
    store.reserve_inflight(
        make_idempotency_key(intent),
        build_inflight_record(
            first_seen_utc=reserved_at,
            reserved_at_utc=reserved_at,
            reservation_token=1,
        ),
    )

    class BrokenClock:
        def now_utc(self) -> datetime:
            raise RuntimeError("clock_down")

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
        clock=BrokenClock(),
        inflight_ttl_seconds=600,
    )

    assert broker.submitted == []
    assert decision.action == "blocked"
    assert decision.reason == "idempotency_clock_error"
