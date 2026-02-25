from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import random
import socket
from typing import Any, Callable, Iterable, Literal, Sequence
from unittest.mock import patch

from .canonical import canonicalize_timestamp_utc
from .models import (
    FeeModel,
    FundingDataMissingError,
    FundingModel,
    LiquidationModel,
    PositionAccounting,
    PositionInvariantError,
    S2ModelError,
    SlippageBucket,
    SlippageModel,
    funding_transfer_quote,
)


DecisionAction = Literal["LONG", "SHORT", "FLAT", "HOLD"]
KillSwitchMode = Literal["SAFE_MODE", "FLATTEN"]
StrategyFn = Callable[["BarCloseEvent", "CoreStateView", random.Random], DecisionAction]
RiskFn = Callable[
    ["BarCloseEvent", "CoreStateView", DecisionAction, random.Random], tuple[bool, str | None]
]
DECISION_RECORD_SCHEMA = "s2/decision_records/v1"
RISK_CHECK_SCHEMA = "s2/risk_checks/v1"
SIMULATED_ORDER_SCHEMA = "s2/simulated_orders/v1"
SIMULATED_FILL_SCHEMA = "s2/simulated_fills/v1"
POSITION_TIMELINE_SCHEMA = "s2/position_timeline/v1"
RISK_EVENT_SCHEMA = "s2/risk_events/v1"
FUNDING_TRANSFER_SCHEMA = "s2/funding_transfers/v1"


class S2CoreError(RuntimeError):
    pass


class NetworkDisabledError(S2CoreError):
    def __init__(self, operation: str):
        super().__init__(f"network_disabled:{operation}")
        self.operation = operation


@dataclass(frozen=True)
class Bar:
    ts_utc: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class BarCloseEvent:
    seq: int
    bar: Bar


@dataclass(frozen=True)
class CoreStateView:
    seq: int
    ts_utc: str
    symbol: str
    timeframe: str
    mark_price: float
    position_qty: float
    avg_entry_price: float
    cash_balance: float
    equity: float
    seed: int


@dataclass(frozen=True)
class S2RiskCaps:
    max_leverage: float = 1_000.0
    max_position_notional_quote: float = 1_000_000_000_000.0
    max_daily_loss_quote: float = 1_000_000_000_000.0
    max_drawdown_ratio: float = 1_000.0
    max_orders_per_window: int = 1_000_000
    order_window_bars: int = 1_440


@dataclass(frozen=True)
class S2KillSwitchConfig:
    mode: KillSwitchMode = "FLATTEN"
    manual_trigger_event_seq: int | None = None


@dataclass(frozen=True)
class S2CoreConfig:
    symbol: str = "BTCUSDT"
    timeframe: str = "1m"
    seed: int = 0
    initial_cash_quote: float = 10_000.0
    target_position_qty: float = 1.0
    fee_model: FeeModel = field(default_factory=FeeModel)
    slippage_model: SlippageModel = field(
        default_factory=lambda: SlippageModel(
            buckets=(
                SlippageBucket(max_notional_quote=10_000.0, bps=1.0),
                SlippageBucket(max_notional_quote=100_000.0, bps=2.0),
                SlippageBucket(max_notional_quote=None, bps=3.0),
            ),
            stress_multiplier=1.0,
        )
    )
    funding_model: FundingModel = field(default_factory=FundingModel)
    liquidation_model: LiquidationModel = field(default_factory=LiquidationModel)
    risk_caps: S2RiskCaps = field(default_factory=S2RiskCaps)
    kill_switch: S2KillSwitchConfig = field(default_factory=S2KillSwitchConfig)


@dataclass(frozen=True)
class S2CoreResult:
    seed: int
    decision_records: list[dict[str, Any]]
    risk_checks: list[dict[str, Any]]
    simulated_orders: list[dict[str, Any]]
    simulated_fills: list[dict[str, Any]]
    position_timeline: list[dict[str, Any]]
    risk_events: list[dict[str, Any]]
    funding_transfers: list[dict[str, Any]]
    cost_breakdown: dict[str, float]
    final_state: dict[str, Any]


def _parse_utc(ts_utc: str) -> datetime:
    text = str(ts_utc).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_utc(dt: datetime) -> str:
    text = dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text


def _coerce_bar(raw: Bar | dict[str, Any]) -> Bar:
    if isinstance(raw, Bar):
        return Bar(
            ts_utc=canonicalize_timestamp_utc(raw.ts_utc),
            open=float(raw.open),
            high=float(raw.high),
            low=float(raw.low),
            close=float(raw.close),
            volume=float(raw.volume),
        )
    if not isinstance(raw, dict):
        raise S2CoreError("bar_invalid_payload")
    try:
        bar = Bar(
            ts_utc=str(raw["ts_utc"]),
            open=float(raw["open"]),
            high=float(raw["high"]),
            low=float(raw["low"]),
            close=float(raw["close"]),
            volume=float(raw["volume"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise S2CoreError("bar_invalid_payload") from exc
    bar = Bar(
        ts_utc=canonicalize_timestamp_utc(bar.ts_utc),
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
    )
    if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
        raise S2CoreError("bar_nonpositive_price")
    return bar


class BarCloseScheduler:
    def __init__(self, bars: Iterable[Bar | dict[str, Any]]):
        normalized = [_coerce_bar(row) for row in bars]
        if not normalized:
            raise S2CoreError("bar_series_empty")
        normalized.sort(key=lambda item: _parse_utc(item.ts_utc))
        self._bars = normalized
        for idx in range(1, len(self._bars)):
            prior = _parse_utc(self._bars[idx - 1].ts_utc)
            curr = _parse_utc(self._bars[idx].ts_utc)
            if curr <= prior:
                raise S2CoreError("bar_series_not_strictly_increasing")

    def events(self) -> list[BarCloseEvent]:
        return [BarCloseEvent(seq=idx, bar=bar) for idx, bar in enumerate(self._bars)]


@contextmanager
def no_network_simulation_guard() -> Any:
    def _blocked_create_connection(*args: Any, **kwargs: Any) -> Any:
        raise NetworkDisabledError("socket.create_connection")

    def _blocked_getaddrinfo(*args: Any, **kwargs: Any) -> Any:
        raise NetworkDisabledError("socket.getaddrinfo")

    def _blocked_socket_connect(*args: Any, **kwargs: Any) -> Any:
        raise NetworkDisabledError("socket.connect")

    with (
        patch("socket.create_connection", _blocked_create_connection),
        patch("socket.getaddrinfo", _blocked_getaddrinfo),
        patch.object(socket.socket, "connect", _blocked_socket_connect),
    ):
        yield


def _coerce_action(value: str) -> DecisionAction:
    text = str(value).strip().upper()
    if text not in {"LONG", "SHORT", "FLAT", "HOLD"}:
        raise S2CoreError("strategy_invalid_action")
    return text  # type: ignore[return-value]


def _default_strategy(
    event: BarCloseEvent, state: CoreStateView, rng: random.Random
) -> DecisionAction:
    del event, state, rng
    return "HOLD"


def _default_risk(
    event: BarCloseEvent, state: CoreStateView, action: DecisionAction, rng: random.Random
) -> tuple[bool, str | None]:
    del event, state, action, rng
    return True, None


def _target_qty(action: DecisionAction, *, current_qty: float, config: S2CoreConfig) -> float:
    base = abs(float(config.target_position_qty))
    if action == "LONG":
        return base
    if action == "SHORT":
        return -base
    if action == "FLAT":
        return 0.0
    return float(current_qty)


def _state_view(
    *,
    event: BarCloseEvent,
    position: PositionAccounting,
    cash_quote: float,
    config: S2CoreConfig,
) -> CoreStateView:
    equity = float(cash_quote) + float(position.unrealized_pnl)
    return CoreStateView(
        seq=event.seq,
        ts_utc=event.bar.ts_utc,
        symbol=config.symbol,
        timeframe=config.timeframe,
        mark_price=float(event.bar.close),
        position_qty=float(position.qty),
        avg_entry_price=float(position.avg_entry_price),
        cash_balance=float(cash_quote),
        equity=float(equity),
        seed=int(config.seed),
    )


def run_s2_core_loop(
    *,
    bars: Sequence[Bar | dict[str, Any]],
    config: S2CoreConfig,
    strategy_fn: StrategyFn | None = None,
    risk_fn: RiskFn | None = None,
) -> S2CoreResult:
    scheduler = BarCloseScheduler(bars)
    strategy = strategy_fn or _default_strategy
    risk_eval = risk_fn or _default_risk
    rng = random.Random(int(config.seed))

    cash_quote = float(config.initial_cash_quote)
    position = PositionAccounting()

    decision_records: list[dict[str, Any]] = []
    risk_checks: list[dict[str, Any]] = []
    simulated_orders: list[dict[str, Any]] = []
    simulated_fills: list[dict[str, Any]] = []
    position_timeline: list[dict[str, Any]] = []
    risk_events: list[dict[str, Any]] = []
    funding_transfers: list[dict[str, Any]] = []

    order_seq = 0
    fill_seq = 0
    events = scheduler.events()
    peak_equity = float(cash_quote)
    orders_window: list[int] = []
    kill_switch_active = False
    kill_switch_reason_code = ""

    try:
        with no_network_simulation_guard():

            def _prune_order_window(event_seq: int) -> None:
                window = max(int(config.risk_caps.order_window_bars), 1)
                cutoff = int(event_seq) - window + 1
                while orders_window and orders_window[0] < cutoff:
                    orders_window.pop(0)

            def _activate_kill(event: BarCloseEvent, reason_code: str, detail: str) -> None:
                nonlocal kill_switch_active, kill_switch_reason_code
                if kill_switch_active:
                    return
                kill_switch_active = True
                kill_switch_reason_code = reason_code
                risk_events.append(
                    {
                        "schema_version": RISK_EVENT_SCHEMA,
                        "event_seq": event.seq,
                        "ts_utc": event.bar.ts_utc,
                        "reason_code": reason_code,
                        "detail": detail,
                    }
                )

            def _execute_order(
                event: BarCloseEvent,
                qty_delta: float,
                *,
                decision: str,
                order_type: str,
                extra_fill_fields: dict[str, Any] | None = None,
            ) -> None:
                nonlocal order_seq, fill_seq, cash_quote
                side = "BUY" if qty_delta > 0 else "SELL"
                mark_price = float(event.bar.close)
                order_seq += 1
                order_id = f"ord-{event.seq:06d}-{order_seq:04d}"
                notional_ref = abs(qty_delta * mark_price)
                fill_price = config.slippage_model.apply(
                    mark_price, side=side, notional_quote=notional_ref
                )
                notional_fill = abs(qty_delta * fill_price)
                fee_quote = config.fee_model.fee_for_notional(notional_fill, liquidity="taker")
                slippage_quote = abs(qty_delta) * abs(fill_price - mark_price)

                simulated_orders.append(
                    {
                        "schema_version": SIMULATED_ORDER_SCHEMA,
                        "order_id": order_id,
                        "event_seq": event.seq,
                        "ts_utc": event.bar.ts_utc,
                        "symbol": config.symbol,
                        "side": side,
                        "qty": float(qty_delta),
                        "decision": decision,
                        "order_type": order_type,
                    }
                )

                fill_seq += 1
                fill_id = f"fill-{event.seq:06d}-{fill_seq:04d}"
                realized_delta = position.apply_fill(qty_delta, fill_price)
                cash_quote += realized_delta
                cash_quote -= fee_quote
                position.cumulative_fees += fee_quote
                position.cumulative_slippage += slippage_quote

                payload: dict[str, Any] = {
                    "schema_version": SIMULATED_FILL_SCHEMA,
                    "fill_id": fill_id,
                    "order_id": order_id,
                    "event_seq": event.seq,
                    "ts_utc": event.bar.ts_utc,
                    "symbol": config.symbol,
                    "side": side,
                    "qty": float(qty_delta),
                    "reference_price": mark_price,
                    "fill_price": fill_price,
                    "fee_quote": fee_quote,
                    "slippage_quote": slippage_quote,
                    "realized_pnl_delta_quote": realized_delta,
                }
                if extra_fill_fields:
                    payload.update(extra_fill_fields)
                simulated_fills.append(payload)
                orders_window.append(event.seq)

            for event in events:
                mark_price = float(event.bar.close)
                position.mark_to_market(mark_price)
                equity_quote = float(cash_quote) + float(position.unrealized_pnl)
                if equity_quote > peak_equity:
                    peak_equity = equity_quote

                if config.kill_switch.manual_trigger_event_seq is not None and event.seq == int(
                    config.kill_switch.manual_trigger_event_seq
                ):
                    _activate_kill(event, "manual_trigger", "manual kill-switch event configured")

                state_pre = _state_view(
                    event=event, position=position, cash_quote=cash_quote, config=config
                )
                if kill_switch_active:
                    action = "HOLD"
                else:
                    action = _coerce_action(strategy(event, state_pre, rng))
                decision_records.append(
                    {
                        "schema_version": DECISION_RECORD_SCHEMA,
                        "event_seq": event.seq,
                        "ts_utc": event.bar.ts_utc,
                        "decision": action,
                        "decision_time": "bar_close",
                        "seed": int(config.seed),
                        "kill_switch_active": bool(kill_switch_active),
                    }
                )

                if kill_switch_active:
                    allowed, risk_reason = False, "kill_switch_active"
                else:
                    allowed, risk_reason = risk_eval(event, state_pre, action, rng)
                risk_checks.append(
                    {
                        "schema_version": RISK_CHECK_SCHEMA,
                        "event_seq": event.seq,
                        "ts_utc": event.bar.ts_utc,
                        "decision": action,
                        "allowed": bool(allowed),
                        "reason": risk_reason or "",
                        "evaluation_time": "bar_close",
                    }
                )
                if not allowed:
                    risk_events.append(
                        {
                            "schema_version": RISK_EVENT_SCHEMA,
                            "event_seq": event.seq,
                            "ts_utc": event.bar.ts_utc,
                            "reason_code": "risk_blocked",
                            "detail": risk_reason or "risk_veto",
                        }
                    )
                    action = "HOLD"

                desired_qty = _target_qty(action, current_qty=position.qty, config=config)
                qty_delta = desired_qty - position.qty
                will_trade = abs(qty_delta) > 1e-12

                if not kill_switch_active:
                    _prune_order_window(event.seq)
                    target_notional = abs(desired_qty * mark_price)
                    effective_equity = max(abs(equity_quote), 1e-9)
                    target_leverage = (
                        target_notional / effective_equity if target_notional > 0 else 0.0
                    )
                    daily_loss = max(0.0, float(config.initial_cash_quote) - equity_quote)
                    drawdown = (
                        max(0.0, (peak_equity - equity_quote) / peak_equity)
                        if peak_equity > 0
                        else 0.0
                    )
                    if target_leverage > float(config.risk_caps.max_leverage):
                        _activate_kill(
                            event, "max_leverage_breach", f"target_leverage={target_leverage:.8f}"
                        )
                    elif target_notional > float(config.risk_caps.max_position_notional_quote):
                        _activate_kill(
                            event,
                            "max_position_notional_breach",
                            f"target_notional={target_notional:.8f}",
                        )
                    elif daily_loss > float(config.risk_caps.max_daily_loss_quote):
                        _activate_kill(
                            event, "max_daily_loss_breach", f"daily_loss={daily_loss:.8f}"
                        )
                    elif drawdown > float(config.risk_caps.max_drawdown_ratio):
                        _activate_kill(event, "max_drawdown_breach", f"drawdown={drawdown:.8f}")
                    elif will_trade and len(orders_window) >= int(
                        config.risk_caps.max_orders_per_window
                    ):
                        _activate_kill(
                            event,
                            "max_orders_per_window_breach",
                            f"orders_in_window={len(orders_window)}",
                        )
                    if kill_switch_active:
                        desired_qty = position.qty
                        qty_delta = 0.0

                if (
                    kill_switch_active
                    and config.kill_switch.mode == "FLATTEN"
                    and abs(position.qty) > 1e-12
                ):
                    _execute_order(
                        event,
                        -position.qty,
                        decision="FLAT",
                        order_type="KILL_SWITCH_FLATTEN",
                        extra_fill_fields={"is_kill_switch_flatten": True},
                    )
                    risk_events.append(
                        {
                            "schema_version": RISK_EVENT_SCHEMA,
                            "event_seq": event.seq,
                            "ts_utc": event.bar.ts_utc,
                            "reason_code": "kill_switch_flatten",
                            "detail": kill_switch_reason_code or "kill_switch_active",
                        }
                    )

                if not kill_switch_active and abs(qty_delta) > 1e-12:
                    _execute_order(event, qty_delta, decision=action, order_type="MARKET_SIM")

                funding_rate = config.funding_model.funding_rate(
                    event.bar.ts_utc, has_open_position=position.qty != 0.0
                )
                if funding_rate is not None and position.qty != 0.0:
                    transfer = funding_transfer_quote(position.qty, mark_price, funding_rate)
                    cash_quote += transfer
                    position.cumulative_funding += transfer
                    funding_transfers.append(
                        {
                            "schema_version": FUNDING_TRANSFER_SCHEMA,
                            "event_seq": event.seq,
                            "ts_utc": event.bar.ts_utc,
                            "funding_rate": float(funding_rate),
                            "position_qty": float(position.qty),
                            "mark_price": mark_price,
                            "transfer_quote": float(transfer),
                        }
                    )

                position.mark_to_market(mark_price)
                equity_quote = float(cash_quote) + float(position.unrealized_pnl)
                notional_quote = abs(float(position.qty) * mark_price)
                if config.liquidation_model.should_liquidate(
                    equity_quote=equity_quote,
                    notional_quote=notional_quote,
                ):
                    if abs(position.qty) > 1e-12:
                        _activate_kill(
                            event,
                            "risk_breach_liquidation",
                            "conservative liquidation threshold breached",
                        )
                        _execute_order(
                            event,
                            -position.qty,
                            decision="FLAT",
                            order_type="LIQUIDATION",
                            extra_fill_fields={"is_liquidation": True},
                        )
                        position.liquidation_count += 1
                        risk_events.append(
                            {
                                "schema_version": RISK_EVENT_SCHEMA,
                                "event_seq": event.seq,
                                "ts_utc": event.bar.ts_utc,
                                "reason_code": "liquidation_triggered",
                                "detail": "conservative_threshold_breach",
                            }
                        )

                position.mark_to_market(mark_price)
                equity_quote = float(cash_quote) + float(position.unrealized_pnl)
                invariants_ok = True
                try:
                    position.assert_invariants()
                except PositionInvariantError:
                    invariants_ok = False
                    _activate_kill(event, "data_integrity_failure", "position invariant failure")
                    raise
                position_timeline.append(
                    {
                        "schema_version": POSITION_TIMELINE_SCHEMA,
                        "event_seq": event.seq,
                        "ts_utc": event.bar.ts_utc,
                        "mark_price": mark_price,
                        "position_qty": float(position.qty),
                        "avg_entry_price": float(position.avg_entry_price),
                        "realized_pnl_quote": float(position.realized_pnl),
                        "unrealized_pnl_quote": float(position.unrealized_pnl),
                        "cash_balance_quote": float(cash_quote),
                        "equity_quote": float(equity_quote),
                        "invariants_ok": invariants_ok,
                        "kill_switch_active": bool(kill_switch_active),
                        "kill_switch_reason_code": kill_switch_reason_code,
                    }
                )
    except (S2ModelError, FundingDataMissingError, PositionInvariantError) as exc:
        raise S2CoreError(str(exc)) from exc

    total_funding = float(position.cumulative_funding)
    total_fees = float(position.cumulative_fees)
    total_slippage = float(position.cumulative_slippage)
    cost_breakdown = {
        "fees_quote": total_fees,
        "slippage_quote": total_slippage,
        "funding_quote": total_funding,
        "total_cost_quote": total_fees + total_slippage - total_funding,
    }

    final_state = {
        "cash_balance_quote": float(cash_quote),
        "position_qty": float(position.qty),
        "avg_entry_price": float(position.avg_entry_price),
        "realized_pnl_quote": float(position.realized_pnl),
        "unrealized_pnl_quote": float(position.unrealized_pnl),
        "equity_quote": float(cash_quote + position.unrealized_pnl),
        "liquidation_count": float(position.liquidation_count),
        "kill_switch_active": bool(kill_switch_active),
        "kill_switch_reason_code": kill_switch_reason_code,
        "kill_switch_mode": str(config.kill_switch.mode),
    }

    return S2CoreResult(
        seed=int(config.seed),
        decision_records=decision_records,
        risk_checks=risk_checks,
        simulated_orders=simulated_orders,
        simulated_fills=simulated_fills,
        position_timeline=position_timeline,
        risk_events=risk_events,
        funding_transfers=funding_transfers,
        cost_breakdown=cost_breakdown,
        final_state=final_state,
    )


def bars_from_ohlcv_rows(rows: Sequence[dict[str, Any]]) -> list[Bar]:
    bars: list[Bar] = []
    for row in rows:
        if "timestamp" in row and "ts_utc" not in row:
            ts = _format_utc(_parse_utc(str(row["timestamp"])))
        else:
            ts = _format_utc(_parse_utc(str(row["ts_utc"])))
        bars.append(
            Bar(
                ts_utc=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
            )
        )
    return bars
