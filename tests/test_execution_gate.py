"""Tests for centralized risk gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from execution.audit import DecisionWriter
from execution.brokers import PaperBroker
from execution.engine import ExecutionEngine
from execution.gate import GateResult, gate_execution
from execution.idempotency import IdempotencyStore
from execution.locks import RiskLocks
from execution.types import ExecutionDecision, IntentSide, OrderIntent
from risk.contracts import RiskInputs
from risk.state_machine import RiskConfig, RiskDecision, RiskState
from risk.types import Permission
from risk.veto import risk_veto


pytestmark = pytest.mark.unit


def _config() -> RiskConfig:
    return RiskConfig(missing_red=0.1, atr_yellow=0.02, atr_red=0.05)


def _intent() -> OrderIntent:
    return OrderIntent(
        event_id="evt-1",
        intent_id="intent-1",
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


def test_gate_blocks_on_red() -> None:
    inputs = RiskInputs(
        symbol="BTCUSDT",
        timeframe="1h",
        as_of="2024-01-01T00:00:00+00:00",
        atr_pct=0.1,
        realized_vol=None,
        missing_fraction=0.0,
        timestamps_valid=True,
        latest_metrics_valid=True,
        invalid_index=False,
        invalid_close=False,
    )
    result = gate_execution(inputs, _config())
    assert result.allowed is False
    assert result.decision.state is RiskState.RED
    assert result.reason == "risk_veto"


def test_engine_invokes_gate_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called = {"count": 0}

    def _fake_gate(inputs: RiskInputs, cfg: RiskConfig) -> GateResult:
        called["count"] += 1
        decision = RiskDecision(
            state=RiskState.RED,
            reasons=["forced_red"],
            snapshot={"forced": True},
        )
        return GateResult(
            allowed=False,
            decision=decision,
            audit_event=risk_veto(inputs, cfg)[1],
            reason="risk_veto",
        )

    monkeypatch.setattr("execution.engine.gate_execution", _fake_gate)

    broker = PaperBroker()
    engine = ExecutionEngine(
        broker=broker,
        decision_writer=DecisionWriter(tmp_path / "decisions.jsonl"),
        idempotency=IdempotencyStore(),
    )
    decision: ExecutionDecision = engine.handle_intent(
        intent=_intent(),
        risk_state=RiskState.GREEN,
        permission=Permission.ALLOW,
        risk_inputs=RiskInputs(
            symbol="BTCUSDT",
            timeframe="1h",
            as_of="2024-01-01T00:00:00+00:00",
            atr_pct=0.1,
            realized_vol=None,
            missing_fraction=0.0,
            timestamps_valid=True,
            latest_metrics_valid=True,
            invalid_index=False,
            invalid_close=False,
        ),
        risk_config=_config(),
        locks=_locks(),
        current_exposure=0.0,
        trades_today=0,
        data_snapshot_hash="data",
        feature_snapshot_hash="features",
        strategy_id="strat-1",
    )
    assert called["count"] == 1
    assert decision.action == "blocked"
    assert broker.submitted == []


def test_no_duplicate_veto_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _allow_gate(inputs: RiskInputs, cfg: RiskConfig) -> GateResult:
        decision = RiskDecision(
            state=RiskState.GREEN,
            reasons=[],
            snapshot={"ok": True},
        )
        return GateResult(
            allowed=True,
            decision=decision,
            audit_event=risk_veto(inputs, cfg)[1],
            reason=None,
        )

    monkeypatch.setattr("execution.engine.gate_execution", _allow_gate)

    broker = PaperBroker()
    engine = ExecutionEngine(
        broker=broker,
        decision_writer=DecisionWriter(tmp_path / "decisions.jsonl"),
        idempotency=IdempotencyStore(),
    )
    decision: ExecutionDecision = engine.handle_intent(
        intent=_intent(),
        risk_state=RiskState.RED,
        permission=Permission.BLOCK,
        risk_inputs=RiskInputs(
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
        ),
        risk_config=_config(),
        locks=_locks(),
        current_exposure=0.0,
        trades_today=0,
        data_snapshot_hash="data",
        feature_snapshot_hash="features",
        strategy_id="strat-1",
    )
    assert decision.action != "blocked"
