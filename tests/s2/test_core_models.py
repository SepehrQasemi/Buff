from __future__ import annotations

from datetime import datetime, timedelta, timezone
import socket

import pytest

from s2.core import (
    Bar,
    NetworkDisabledError,
    S2CoreConfig,
    S2CoreError,
    run_s2_core_loop,
)
from s2.models import (
    FeeModel,
    FundingModel,
    LiquidationModel,
    SlippageBucket,
    SlippageModel,
)


def _bars(prices: list[float], *, start: str = "2026-02-01T00:00:00Z") -> list[Bar]:
    if start.endswith("Z"):
        start = start[:-1] + "+00:00"
    start_dt = datetime.fromisoformat(start).astimezone(timezone.utc)
    rows: list[Bar] = []
    for idx, price in enumerate(prices):
        ts = (
            (start_dt + timedelta(minutes=idx)).isoformat(timespec="seconds").replace("+00:00", "Z")
        )
        rows.append(
            Bar(
                ts_utc=ts,
                open=float(price),
                high=float(price),
                low=float(price),
                close=float(price),
                volume=1.0,
            )
        )
    return rows


def _sequence_strategy(actions: list[str]):
    def _fn(event, state, rng):
        del state, rng
        if event.seq < len(actions):
            return actions[event.seq]
        return "HOLD"

    return _fn


def _allow_all(event, state, action, rng):
    del event, state, action, rng
    return True, None


def test_funding_correctness_and_seed_recorded() -> None:
    bars = _bars([100.0, 102.0, 101.0])
    rates = {bar.ts_utc: 0.001 for bar in bars}
    config = S2CoreConfig(
        seed=7,
        initial_cash_quote=1_000.0,
        target_position_qty=1.0,
        fee_model=FeeModel(maker_bps=0.0, taker_bps=0.0),
        slippage_model=SlippageModel(buckets=(SlippageBucket(max_notional_quote=None, bps=0.0),)),
        funding_model=FundingModel(interval_minutes=1, rates_by_ts_utc=rates),
        liquidation_model=LiquidationModel(
            maintenance_margin_ratio=0.001, conservative_buffer_ratio=0.0
        ),
    )

    result = run_s2_core_loop(
        bars=bars,
        config=config,
        strategy_fn=_sequence_strategy(["LONG", "HOLD", "HOLD"]),
        risk_fn=_allow_all,
    )

    transfers = [row["transfer_quote"] for row in result.funding_transfers]
    assert len(transfers) == 3
    assert sum(transfers) == pytest.approx(-(100.0 + 102.0 + 101.0) * 0.001)
    assert result.seed == 7


def test_missing_critical_funding_window_fails_closed() -> None:
    bars = _bars([100.0, 101.0, 102.0])
    rates = {bars[0].ts_utc: 0.001, bars[2].ts_utc: 0.001}
    config = S2CoreConfig(
        initial_cash_quote=1_000.0,
        target_position_qty=1.0,
        fee_model=FeeModel(maker_bps=0.0, taker_bps=0.0),
        slippage_model=SlippageModel(buckets=(SlippageBucket(max_notional_quote=None, bps=0.0),)),
        funding_model=FundingModel(interval_minutes=1, rates_by_ts_utc=rates),
    )

    with pytest.raises(S2CoreError, match="missing_critical_funding_window"):
        run_s2_core_loop(
            bars=bars,
            config=config,
            strategy_fn=_sequence_strategy(["LONG", "HOLD", "HOLD"]),
            risk_fn=_allow_all,
        )


def test_conservative_liquidation_trigger() -> None:
    bars = _bars([100.0, 20.0, 19.0])
    config = S2CoreConfig(
        initial_cash_quote=5.0,
        target_position_qty=1.0,
        fee_model=FeeModel(maker_bps=0.0, taker_bps=0.0),
        slippage_model=SlippageModel(buckets=(SlippageBucket(max_notional_quote=None, bps=0.0),)),
        funding_model=FundingModel(interval_minutes=0),
        liquidation_model=LiquidationModel(
            maintenance_margin_ratio=0.01, conservative_buffer_ratio=0.1
        ),
    )

    result = run_s2_core_loop(
        bars=bars,
        config=config,
        strategy_fn=_sequence_strategy(["LONG", "HOLD", "HOLD"]),
        risk_fn=_allow_all,
    )

    reason_codes = [row["reason_code"] for row in result.risk_events]
    assert "liquidation_triggered" in reason_codes
    assert result.final_state["position_qty"] == pytest.approx(0.0)
    assert result.final_state["liquidation_count"] == pytest.approx(1.0)


def test_fee_and_slippage_accounting() -> None:
    bars = _bars([100.0, 100.0, 100.0])
    config = S2CoreConfig(
        initial_cash_quote=1_000.0,
        target_position_qty=1.0,
        fee_model=FeeModel(maker_bps=0.0, taker_bps=10.0),
        slippage_model=SlippageModel(buckets=(SlippageBucket(max_notional_quote=None, bps=10.0),)),
        funding_model=FundingModel(interval_minutes=0),
        liquidation_model=LiquidationModel(
            maintenance_margin_ratio=0.001, conservative_buffer_ratio=0.0
        ),
    )

    result = run_s2_core_loop(
        bars=bars,
        config=config,
        strategy_fn=_sequence_strategy(["LONG", "FLAT", "HOLD"]),
        risk_fn=_allow_all,
    )

    assert result.cost_breakdown["fees_quote"] == pytest.approx(0.2, abs=1e-6)
    assert result.cost_breakdown["slippage_quote"] == pytest.approx(0.2, abs=1e-6)
    assert result.final_state["realized_pnl_quote"] == pytest.approx(-0.2, abs=1e-6)


def test_position_invariants_hold_across_flips() -> None:
    bars = _bars([100.0, 101.0, 99.0, 102.0, 100.0])
    config = S2CoreConfig(
        initial_cash_quote=1_000.0,
        target_position_qty=1.0,
        fee_model=FeeModel(maker_bps=0.0, taker_bps=0.0),
        slippage_model=SlippageModel(buckets=(SlippageBucket(max_notional_quote=None, bps=0.0),)),
        funding_model=FundingModel(interval_minutes=0),
    )
    result = run_s2_core_loop(
        bars=bars,
        config=config,
        strategy_fn=_sequence_strategy(["LONG", "SHORT", "FLAT", "LONG", "FLAT"]),
        risk_fn=_allow_all,
    )
    assert result.position_timeline
    assert all(row["invariants_ok"] for row in result.position_timeline)


def test_strategy_and_risk_evaluated_once_at_each_bar_close() -> None:
    bars = _bars([100.0, 101.0, 102.0, 103.0])
    strategy_seen: list[str] = []
    risk_seen: list[str] = []

    def _strategy(event, state, rng):
        del state, rng
        strategy_seen.append(event.bar.ts_utc)
        return "HOLD"

    def _risk(event, state, action, rng):
        del state, action, rng
        risk_seen.append(event.bar.ts_utc)
        return True, None

    config = S2CoreConfig(
        fee_model=FeeModel(maker_bps=0.0, taker_bps=0.0),
        slippage_model=SlippageModel(buckets=(SlippageBucket(max_notional_quote=None, bps=0.0),)),
        funding_model=FundingModel(interval_minutes=0),
    )

    result = run_s2_core_loop(bars=bars, config=config, strategy_fn=_strategy, risk_fn=_risk)
    assert len(result.decision_records) == len(bars)
    assert len(strategy_seen) == len(bars)
    assert len(risk_seen) == len(bars)


def test_no_network_calls_allowed_in_simulation_path() -> None:
    bars = _bars([100.0, 101.0])
    config = S2CoreConfig(
        fee_model=FeeModel(maker_bps=0.0, taker_bps=0.0),
        slippage_model=SlippageModel(buckets=(SlippageBucket(max_notional_quote=None, bps=0.0),)),
        funding_model=FundingModel(interval_minutes=0),
    )

    def _network_strategy(event, state, rng):
        del state, rng
        if event.seq == 0:
            socket.getaddrinfo("example.com", 443)
        return "HOLD"

    with pytest.raises(NetworkDisabledError):
        run_s2_core_loop(
            bars=bars, config=config, strategy_fn=_network_strategy, risk_fn=_allow_all
        )
