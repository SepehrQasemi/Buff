from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class EngineConfig:
    strategy_id: str
    strategy_params: dict[str, Any]
    symbol: str
    timeframe: str
    risk_level: int
    commission_bps: float
    slippage_bps: float
    initial_equity: float


@dataclass(frozen=True)
class EngineResult:
    decisions: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    equity_curve: list[dict[str, Any]]
    metrics: dict[str, Any]


def _format_ts(value: pd.Timestamp) -> str:
    if isinstance(value, pd.Timestamp):
        dt = value.to_pydatetime()
    else:
        dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    text = dt.isoformat(timespec="milliseconds")
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text


def _risk_fraction(level: int) -> float:
    return float(max(min(int(level), 5), 1) * 0.1)


def _commission_cost(qty: float, price: float, commission_bps: float) -> float:
    if commission_bps <= 0.0:
        return 0.0
    return abs(qty * price) * (commission_bps / 10_000.0)


def _apply_slippage(price: float, side: str, slippage_bps: float) -> float:
    if slippage_bps <= 0.0:
        return float(price)
    if side == "BUY":
        return float(price) * (1.0 + slippage_bps / 10_000.0)
    return float(price) * (1.0 - slippage_bps / 10_000.0)


def _signal_actions_hold(count: int) -> list[str]:
    actions = ["HOLD"] * count
    if count > 0:
        actions[0] = "ENTER_LONG"
        actions[-1] = "EXIT_LONG"
    return actions


def _signal_actions_ma_cross(df: pd.DataFrame, params: dict[str, Any]) -> list[str]:
    count = len(df)
    actions = ["HOLD"] * count
    if count < 2:
        return actions

    fast = int(params.get("fast_period", 10))
    slow = int(params.get("slow_period", 20))
    if fast <= 0 or slow <= 0 or fast >= slow:
        raise ValueError("strategy_params_invalid")

    close = df["close"].astype("float64")
    fast_ma = close.rolling(window=fast, min_periods=fast).mean()
    slow_ma = close.rolling(window=slow, min_periods=slow).mean()

    for idx in range(1, count - 1):
        prev_fast = fast_ma.iloc[idx - 1]
        prev_slow = slow_ma.iloc[idx - 1]
        curr_fast = fast_ma.iloc[idx]
        curr_slow = slow_ma.iloc[idx]
        if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
            continue
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            actions[idx] = "ENTER_LONG"
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            actions[idx] = "EXIT_LONG"
    return actions


def run_engine(df: pd.DataFrame, config: EngineConfig) -> EngineResult:
    if df.empty:
        raise ValueError("engine_empty_data")

    if config.strategy_id == "hold":
        signal_actions = _signal_actions_hold(len(df))
    elif config.strategy_id == "ma_cross":
        signal_actions = _signal_actions_ma_cross(df, config.strategy_params)
    else:
        raise ValueError("strategy_unsupported")

    decisions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []

    cash = float(config.initial_equity)
    position_qty = 0.0
    entry_price = 0.0
    entry_time = None
    entry_commission = 0.0
    risk_fraction = _risk_fraction(config.risk_level)

    open_prices = df["open"].astype("float64").tolist()
    close_prices = df["close"].astype("float64").tolist()
    timestamps = df["ts"].tolist()

    def _enter(price: float, ts_value: pd.Timestamp) -> None:
        nonlocal cash, position_qty, entry_price, entry_time, entry_commission
        effective = _apply_slippage(price, "BUY", config.slippage_bps)
        if effective <= 0:
            return
        qty = (cash * risk_fraction) / effective
        if qty <= 0:
            return
        commission = _commission_cost(qty, effective, config.commission_bps)
        cash -= (qty * effective) + commission
        position_qty = float(qty)
        entry_price = float(effective)
        entry_time = _format_ts(ts_value)
        entry_commission = float(commission)

    def _exit(price: float, ts_value: pd.Timestamp) -> None:
        nonlocal cash, position_qty, entry_price, entry_time, entry_commission
        if position_qty <= 0:
            return
        effective = _apply_slippage(price, "SELL", config.slippage_bps)
        commission = _commission_cost(position_qty, effective, config.commission_bps)
        cash += (position_qty * effective) - commission
        pnl = (effective - entry_price) * position_qty - entry_commission - commission
        fees = entry_commission + commission
        trades.append(
            {
                "entry_time": entry_time,
                "entry_price": float(entry_price),
                "exit_time": _format_ts(ts_value),
                "exit_price": float(effective),
                "qty": float(position_qty),
                "pnl": float(pnl),
                "fees": float(fees),
                "side": "LONG",
            }
        )
        position_qty = 0.0
        entry_price = 0.0
        entry_time = None
        entry_commission = 0.0

    for idx, ts_value in enumerate(timestamps):
        if config.strategy_id == "hold":
            if idx == 0 and position_qty == 0:
                _enter(open_prices[idx], ts_value)
        else:
            if idx > 0:
                prev_action = signal_actions[idx - 1]
                if prev_action == "ENTER_LONG" and position_qty == 0:
                    _enter(open_prices[idx], ts_value)
                elif prev_action == "EXIT_LONG" and position_qty > 0:
                    _exit(open_prices[idx], ts_value)

        action = signal_actions[idx]
        if config.strategy_id == "ma_cross":
            if action == "ENTER_LONG" and position_qty > 0:
                action = "HOLD"
            elif action == "EXIT_LONG" and position_qty == 0:
                action = "HOLD"

        equity = cash + (position_qty * close_prices[idx])
        equity_curve.append({"t": _format_ts(ts_value), "equity": float(equity)})

        if config.strategy_id == "hold":
            if idx == 0:
                action = "ENTER_LONG"
            elif idx == len(timestamps) - 1:
                action = "EXIT_LONG"
            else:
                action = "HOLD"

        decisions.append(
            {
                "schema_version": "dr.v1",
                "run_id": None,
                "seq": idx,
                "ts_utc": _format_ts(ts_value),
                "action": action,
                "price": float(close_prices[idx]),
                "symbol": config.symbol,
                "timeframe": config.timeframe,
                "strategy_id": config.strategy_id,
                "risk_level": int(config.risk_level),
            }
        )

    if position_qty > 0:
        last_idx = len(timestamps) - 1
        _exit(close_prices[last_idx], timestamps[last_idx])
        equity_curve[-1]["equity"] = float(cash)
        if decisions:
            decisions[-1]["action"] = "EXIT_LONG"

    metrics = _compute_metrics(equity_curve, trades, config.initial_equity)

    return EngineResult(
        decisions=decisions,
        trades=trades,
        equity_curve=equity_curve,
        metrics=metrics,
    )


def _compute_metrics(
    equity_curve: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    initial_equity: float,
) -> dict[str, Any]:
    if not equity_curve:
        return {
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "num_records": 0,
            "win_rate": 0.0,
            "initial_equity": float(initial_equity),
            "final_equity": float(initial_equity),
        }

    equities = [float(point["equity"]) for point in equity_curve]
    start = float(initial_equity)
    end = float(equities[-1])
    total_return = 0.0 if start == 0 else (end - start) / start

    peak = equities[0]
    max_drawdown = 0.0
    for value in equities:
        if value > peak:
            peak = value
        drawdown = 0.0 if peak == 0 else (peak - value) / peak
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    pnls = [float(trade.get("pnl", 0.0)) for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    num_records = len(pnls)
    win_rate = 0.0 if num_records == 0 else len(wins) / num_records

    return {
        "total_return": float(total_return),
        "max_drawdown": float(max_drawdown),
        "num_records": int(num_records),
        "win_rate": float(win_rate),
        "initial_equity": float(start),
        "final_equity": float(end),
    }
