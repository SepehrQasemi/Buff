from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pandas as pd

from strategies.builtins.common import (
    ALLOWED_INTENTS,
    BuiltinStrategyDefinition,
    PositionState,
    StrategyContext,
    update_position_extremes,
    validate_history,
)


@dataclass(frozen=True)
class BacktestArtifacts:
    trades: list[dict[str, Any]]
    metrics: dict[str, float | int]
    timeline: list[dict[str, Any]]


def _metrics_from_trades(trades: Sequence[Mapping[str, Any]]) -> dict[str, float | int]:
    pnls = [float(trade.get("pnl", 0.0)) for trade in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_return = sum(pnls)
    num_trades = len(pnls)
    win_rate = 0.0 if num_trades == 0 else len(wins) / num_trades
    avg_win = 0.0 if not wins else sum(wins) / len(wins)
    avg_loss = 0.0 if not losses else sum(losses) / len(losses)
    return {
        "total_return": total_return,
        "num_trades": num_trades,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }


def _intent(result: Mapping[str, Any]) -> str:
    intent = result.get("intent")
    if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
        raise ValueError("strategy_intent_invalid")
    return intent


def _trade_record(
    *,
    entry_index: int,
    exit_index: int,
    entry_price: float,
    exit_price: float,
    side: str,
    index: pd.Index,
) -> dict[str, Any]:
    pnl = exit_price - entry_price if side == "LONG" else entry_price - exit_price
    entry_ts = index[entry_index] if entry_index < len(index) else entry_index
    exit_ts = index[exit_index] if exit_index < len(index) else exit_index
    return {
        "entry_index": entry_index,
        "exit_index": exit_index,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "side": side,
        "pnl": pnl,
        "entry_ts": entry_ts,
        "exit_ts": exit_ts,
    }


def _timeline_event(event_type: str, idx: int, detail: str | None = None) -> dict[str, Any]:
    payload = {"type": event_type, "index": idx}
    if detail:
        payload["detail"] = detail
    return payload


def run_intent_backtest(
    strategy: BuiltinStrategyDefinition,
    ohlcv: pd.DataFrame,
    *,
    params: Mapping[str, Any] | None = None,
    initial_position: PositionState | Mapping[str, Any] | None = None,
) -> BacktestArtifacts:
    history = validate_history(ohlcv)
    index = history.index
    trades: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    schema = strategy.get_schema()
    warmup_bars = int(schema.get("warmup_bars", 0))

    timeline.append(_timeline_event("run_start", 0))
    if warmup_bars > 0 and len(history) >= warmup_bars:
        timeline.append(_timeline_event("warmup_complete", warmup_bars - 1))

    position = None
    if initial_position is not None:
        if isinstance(initial_position, PositionState):
            position = initial_position
        else:
            position = PositionState(
                side=str(initial_position.get("side", "LONG")),
                entry_price=float(
                    initial_position.get("entry_price", float(history["close"].iloc[0]))
                ),
                entry_index=int(initial_position.get("entry_index", 0)),
                max_price=float(initial_position.get("max_price", float(history["high"].iloc[0]))),
                min_price=float(initial_position.get("min_price", float(history["low"].iloc[0]))),
                bars_in_trade=int(initial_position.get("bars_in_trade", 0)),
            )

    for idx in range(len(history)):
        bar_history = history.iloc[: idx + 1]
        ctx = StrategyContext(history=bar_history, params=params or {}, position=position)
        result = strategy.on_bar(ctx)
        intent = _intent(result)
        price = float(bar_history["close"].iloc[-1])

        if intent in {"ENTER_LONG", "ENTER_SHORT"}:
            side = "LONG" if intent == "ENTER_LONG" else "SHORT"
            if position is not None and position.side != side:
                trades.append(
                    _trade_record(
                        entry_index=position.entry_index,
                        exit_index=idx,
                        entry_price=position.entry_price,
                        exit_price=price,
                        side=position.side,
                        index=index,
                    )
                )
                timeline.append(_timeline_event("exit", idx, f"{position.side.lower()}_to_flip"))
                position = None
            if position is None:
                high = float(bar_history["high"].iloc[-1])
                low = float(bar_history["low"].iloc[-1])
                position = PositionState(
                    side=side,
                    entry_price=price,
                    entry_index=idx,
                    max_price=high,
                    min_price=low,
                    bars_in_trade=0,
                )
                timeline.append(_timeline_event("entry", idx, side.lower()))
        elif intent in {"EXIT_LONG", "EXIT_SHORT"}:
            if position is not None and (
                (intent == "EXIT_LONG" and position.side == "LONG")
                or (intent == "EXIT_SHORT" and position.side == "SHORT")
            ):
                trades.append(
                    _trade_record(
                        entry_index=position.entry_index,
                        exit_index=idx,
                        entry_price=position.entry_price,
                        exit_price=price,
                        side=position.side,
                        index=index,
                    )
                )
                timeline.append(_timeline_event("exit", idx, position.side.lower()))
                position = None

        if position is not None:
            high = float(bar_history["high"].iloc[-1])
            low = float(bar_history["low"].iloc[-1])
            position = update_position_extremes(position, high=high, low=low)

    timeline.append(_timeline_event("run_end", len(history) - 1))
    metrics = _metrics_from_trades(trades)

    return BacktestArtifacts(trades=trades, metrics=metrics, timeline=timeline)


__all__ = ["BacktestArtifacts", "run_intent_backtest"]
