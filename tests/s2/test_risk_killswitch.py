from __future__ import annotations

import json
from pathlib import Path

import pytest

from s2.artifacts import S2ArtifactError, S2ArtifactRequest, run_s2_artifact_pack
from s2.core import S2CoreConfig, S2KillSwitchConfig, S2RiskCaps, run_s2_core_loop
from s2.models import FeeModel, FundingModel, LiquidationModel, SlippageBucket, SlippageModel


def _bars(prices: list[float]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, price in enumerate(prices):
        rows.append(
            {
                "ts_utc": f"2026-02-01T00:{idx:02d}:00Z",
                "open": float(price),
                "high": float(price),
                "low": float(price),
                "close": float(price),
                "volume": 1.0,
            }
        )
    return rows


def _core_config(**kwargs) -> S2CoreConfig:
    defaults = dict(
        symbol="BTCUSDT",
        timeframe="1m",
        initial_cash_quote=1_000.0,
        target_position_qty=1.0,
        fee_model=FeeModel(maker_bps=0.0, taker_bps=0.0),
        slippage_model=SlippageModel(buckets=(SlippageBucket(max_notional_quote=None, bps=0.0),)),
        funding_model=FundingModel(interval_minutes=0),
        liquidation_model=LiquidationModel(
            maintenance_margin_ratio=0.001, conservative_buffer_ratio=0.0
        ),
        risk_caps=S2RiskCaps(),
        kill_switch=S2KillSwitchConfig(),
    )
    defaults.update(kwargs)
    return S2CoreConfig(**defaults)


def _strategy(actions: list[str]):
    def _fn(event, state, rng):
        del state, rng
        if event.seq < len(actions):
            return actions[event.seq]
        return "HOLD"

    return _fn


def _allow_all(event, state, action, rng):
    del event, state, action, rng
    return True, None


def test_max_leverage_breach_triggers_kill_switch() -> None:
    config = _core_config(
        initial_cash_quote=100.0,
        target_position_qty=1.0,
        risk_caps=S2RiskCaps(max_leverage=0.5),
    )
    result = run_s2_core_loop(
        bars=_bars([100.0, 100.0]),
        config=config,
        strategy_fn=_strategy(["LONG", "HOLD"]),
        risk_fn=_allow_all,
    )
    assert result.final_state["kill_switch_active"] is True
    assert result.final_state["kill_switch_reason_code"] == "max_leverage_breach"
    assert not result.simulated_orders


def test_max_position_notional_breach_triggers_kill_switch() -> None:
    config = _core_config(
        target_position_qty=1.0,
        risk_caps=S2RiskCaps(max_position_notional_quote=50.0),
    )
    result = run_s2_core_loop(
        bars=_bars([100.0, 100.0]),
        config=config,
        strategy_fn=_strategy(["LONG", "HOLD"]),
        risk_fn=_allow_all,
    )
    assert result.final_state["kill_switch_active"] is True
    assert result.final_state["kill_switch_reason_code"] == "max_position_notional_breach"
    assert not result.simulated_orders


def test_max_daily_loss_breach_flattens_in_kill_switch_mode() -> None:
    config = _core_config(
        risk_caps=S2RiskCaps(max_daily_loss_quote=5.0),
        kill_switch=S2KillSwitchConfig(mode="FLATTEN"),
    )
    result = run_s2_core_loop(
        bars=_bars([100.0, 70.0, 70.0]),
        config=config,
        strategy_fn=_strategy(["LONG", "HOLD", "HOLD"]),
        risk_fn=_allow_all,
    )
    assert result.final_state["kill_switch_active"] is True
    assert result.final_state["kill_switch_reason_code"] == "max_daily_loss_breach"
    assert result.final_state["position_qty"] == pytest.approx(0.0)
    assert any(order["order_type"] == "KILL_SWITCH_FLATTEN" for order in result.simulated_orders)


def test_max_drawdown_breach_triggers_kill_switch() -> None:
    caps = S2RiskCaps(max_daily_loss_quote=1_000_000.0, max_drawdown_ratio=0.01)
    config = _core_config(risk_caps=caps, kill_switch=S2KillSwitchConfig(mode="FLATTEN"))
    result = run_s2_core_loop(
        bars=_bars([100.0, 80.0, 80.0]),
        config=config,
        strategy_fn=_strategy(["LONG", "HOLD", "HOLD"]),
        risk_fn=_allow_all,
    )
    assert result.final_state["kill_switch_active"] is True
    assert result.final_state["kill_switch_reason_code"] == "max_drawdown_breach"
    assert result.final_state["position_qty"] == pytest.approx(0.0)


def test_max_orders_per_window_breach_triggers_kill_switch() -> None:
    config = _core_config(
        risk_caps=S2RiskCaps(max_orders_per_window=1, order_window_bars=10),
        kill_switch=S2KillSwitchConfig(mode="FLATTEN"),
    )
    result = run_s2_core_loop(
        bars=_bars([100.0, 101.0, 102.0]),
        config=config,
        strategy_fn=_strategy(["LONG", "FLAT", "LONG"]),
        risk_fn=_allow_all,
    )
    assert result.final_state["kill_switch_active"] is True
    assert result.final_state["kill_switch_reason_code"] == "max_orders_per_window_breach"
    market_orders = [
        order for order in result.simulated_orders if order["order_type"] == "MARKET_SIM"
    ]
    assert len(market_orders) == 1


def test_manual_trigger_flattens_position() -> None:
    config = _core_config(
        kill_switch=S2KillSwitchConfig(mode="FLATTEN", manual_trigger_event_seq=1),
    )
    result = run_s2_core_loop(
        bars=_bars([100.0, 101.0, 102.0]),
        config=config,
        strategy_fn=_strategy(["LONG", "HOLD", "HOLD"]),
        risk_fn=_allow_all,
    )
    assert result.final_state["kill_switch_active"] is True
    assert result.final_state["kill_switch_reason_code"] == "manual_trigger"
    assert result.final_state["position_qty"] == pytest.approx(0.0)
    assert any(order["order_type"] == "KILL_SWITCH_FLATTEN" for order in result.simulated_orders)


def test_safe_mode_blocks_new_risk_without_flattening() -> None:
    config = _core_config(
        kill_switch=S2KillSwitchConfig(mode="SAFE_MODE", manual_trigger_event_seq=1),
    )
    result = run_s2_core_loop(
        bars=_bars([100.0, 101.0, 102.0]),
        config=config,
        strategy_fn=_strategy(["LONG", "HOLD", "HOLD"]),
        risk_fn=_allow_all,
    )
    assert result.final_state["kill_switch_active"] is True
    assert result.final_state["kill_switch_reason_code"] == "manual_trigger"
    assert result.final_state["position_qty"] == pytest.approx(1.0)
    assert not any(
        order["order_type"] == "KILL_SWITCH_FLATTEN" for order in result.simulated_orders
    )


def test_digest_mismatch_records_kill_switch_reason_code(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    data_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-02-01T00:00:00Z,100,101,99,100.5,10\n"
        "2026-02-01T00:01:00Z,100.5,101.0,100,100.8,9\n",
        encoding="utf-8",
    )
    request = S2ArtifactRequest(
        run_id="digest001",
        symbol="BTCUSDT",
        timeframe="1m",
        seed=3,
        data_path=str(data_path),
        strategy_version="strategy.demo.v1",
        data_sha256="0" * 64,
        strategy_config={"actions": ["LONG", "FLAT"]},
        risk_version="risk.demo.v1",
        risk_config={},
        core_config=_core_config(),
    )

    with pytest.raises(S2ArtifactError, match="INPUT_DIGEST_MISMATCH"):
        run_s2_artifact_pack(request, tmp_path / "out")

    risk_events = (tmp_path / "out" / "digest001" / "risk_events.jsonl").read_text(encoding="utf-8")
    first_event = json.loads(risk_events.splitlines()[0])
    assert first_event["reason_code"] == "digest_mismatch"
