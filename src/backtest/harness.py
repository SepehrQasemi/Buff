from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from audit.decision_records import (
    canonical_json,
    compute_market_state_hash,
    validate_decision_record_v1,
)
from features.build_features import build_features
from buff.features.indicators import atr_wilder, bollinger_bands, ema, rsi_wilder
from features.regime import (
    ATR_PCT_HIGH_QUANTILE,
    ATR_PCT_LOW_QUANTILE,
    EMA_SPREAD_THRESHOLD,
    RSI_BEAR,
    RSI_BULL,
    RSI_SLOPE_THRESHOLD,
)
from risk.contracts import RiskState
from selector.records import selection_to_record
from selector.selector import select_strategy
from strategy_registry import get_strategy, list_strategies, run_strategy


REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


@dataclass(frozen=True)
class BacktestResult:
    trades: pd.DataFrame
    metrics: dict[str, float | int]
    trades_path: Path
    metrics_path: Path
    decision_records_path: Path
    manifest_path: Path


def _iso_utc(ts: pd.Timestamp) -> str:
    value = ts.isoformat()
    if value.endswith("+00:00"):
        return value.replace("+00:00", "Z")
    return value


def _validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        raise ValueError("backtest_input_invalid")
    if not REQUIRED_COLUMNS.issubset(set(df.columns)):
        missing = sorted(REQUIRED_COLUMNS - set(df.columns))
        raise ValueError(f"backtest_missing_columns:{','.join(missing)}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("backtest_index_not_datetime")
    if df.index.tz is None:
        raise ValueError("backtest_index_not_utc")
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    return df


def _bundle_fingerprint(df: pd.DataFrame) -> str:
    payload = f"{len(df)}|{','.join(df.columns)}|{_iso_utc(df.index[0])}|{_iso_utc(df.index[-1])}"
    return sha256(payload.encode("utf-8")).hexdigest()


def _feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")

    bb = bollinger_bands(close, period=20, k=2.0, ddof=0)
    out = pd.DataFrame(
        {
            "close": close,
            "ema_20": ema(close, period=20),
            "ema_50": ema(close, period=50),
            "rsi_14": rsi_wilder(close, period=14),
            "atr_14": atr_wilder(high, low, close, period=14),
            "bb_mid_20_2": bb["mid"],
            "bb_upper_20_2": bb["upper"],
            "bb_lower_20_2": bb["lower"],
        },
        index=df.index,
    )
    out.index.name = df.index.name or "timestamp"
    return out


def _market_state(df: pd.DataFrame) -> pd.DataFrame:
    with_ts = df.reset_index().rename(columns={df.index.name or "index": "timestamp"})
    feats = build_features(with_ts)

    spread = feats.get("ema_spread_20_50_pct")
    if spread is None:
        denom = feats["ema_50"].replace(0.0, float("nan"))
        spread = (feats["ema_20"] - feats["ema_50"]) / denom

    trend_state = pd.Series("flat", index=feats.index, dtype="string")
    trend_state = trend_state.mask(spread > EMA_SPREAD_THRESHOLD, "up")
    trend_state = trend_state.mask(spread < -EMA_SPREAD_THRESHOLD, "down")

    rsi = feats["rsi_14"].astype(float)
    rsi_slope_val = feats["rsi_slope_14_5"].astype(float)
    momentum_state = pd.Series("neutral", index=feats.index, dtype="string")
    bull_mask = (rsi >= RSI_BULL) & (rsi_slope_val >= RSI_SLOPE_THRESHOLD)
    bear_mask = (rsi <= RSI_BEAR) & (rsi_slope_val <= -RSI_SLOPE_THRESHOLD)
    momentum_state = momentum_state.mask(bull_mask, "bull")
    momentum_state = momentum_state.mask(bear_mask, "bear")

    atr_pct = feats["atr_pct"].astype(float)
    vol = pd.Series("mid", index=feats.index, dtype="string")
    # Compute percentile cutoffs using only past bars to avoid look-ahead.
    for idx in range(len(atr_pct)):
        window = atr_pct.iloc[: idx + 1].dropna()
        value = atr_pct.iloc[idx]
        if window.empty or not pd.notna(value):
            continue
        low_cut = float(window.quantile(ATR_PCT_LOW_QUANTILE))
        high_cut = float(window.quantile(ATR_PCT_HIGH_QUANTILE))
        if not (low_cut < high_cut):
            continue
        if value <= low_cut:
            vol.iloc[idx] = "low"
        elif value >= high_cut:
            vol.iloc[idx] = "high"

    structure_state = pd.Series("unknown", index=trend_state.index, dtype="string")
    structure_state = structure_state.mask(trend_state == "flat", "meanrevert")
    structure_state = structure_state.mask(trend_state.isin(["up", "down"]), "breakout")
    out = pd.DataFrame(
        {
            "trend_state": trend_state,
            "momentum_state": momentum_state,
            "volatility_regime": vol,
            "structure_state": structure_state,
        },
        index=feats.index,
    )
    out.index.name = df.index.name or "timestamp"
    return out


def _resolve_strategy_id(name: str) -> str | None:
    matches = [spec for spec in list_strategies() if spec.name == name]
    if not matches:
        if not name.endswith("_V1"):
            fallback = f"{name}_V1"
            matches = [spec for spec in list_strategies() if spec.name == fallback]
        if not matches:
            return None
    chosen = sorted(matches, key=lambda spec: spec.version)[-1]
    return f"{chosen.name}@{chosen.version}"


def _feature_metadata() -> list[dict[str, object]]:
    return [
        {"feature_id": "ema_20", "version": 1, "outputs": ["ema_20"]},
        {"feature_id": "ema_50", "version": 1, "outputs": ["ema_50"]},
        {"feature_id": "rsi_14", "version": 1, "outputs": ["rsi_14"]},
        {"feature_id": "atr_14", "version": 1, "outputs": ["atr_14"]},
        {
            "feature_id": "bbands_20_2",
            "version": 1,
            "outputs": ["bb_mid_20_2", "bb_upper_20_2", "bb_lower_20_2"],
        },
    ]


def _write_trades(path: Path, trades: list[dict[str, object]]) -> Path:
    df = pd.DataFrame(trades)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def _metrics_from_equity(
    equity_curve: list[float], trade_pnls: list[float]
) -> dict[str, float | int]:
    if not equity_curve:
        return {
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "num_trades": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
        }

    start = equity_curve[0]
    end = equity_curve[-1]
    total_return = 0.0 if start == 0 else (end - start) / start

    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        drawdown = 0.0 if peak == 0 else (peak - value) / peak
        if drawdown > max_dd:
            max_dd = drawdown

    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]
    num_trades = len(trade_pnls)
    win_rate = 0.0 if num_trades == 0 else len(wins) / num_trades
    avg_win = 0.0 if not wins else sum(wins) / len(wins)
    avg_loss = 0.0 if not losses else sum(losses) / len(losses)

    return {
        "total_return": total_return,
        "max_drawdown": max_dd,
        "num_trades": num_trades,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }


def _write_json(path: Path, payload: Mapping[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _git_sha() -> str | None:
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        sha = result.stdout.strip()
        return sha or None
    except Exception:
        return None


class _DecisionRecordsWriter:
    def __init__(self, *, out_path: Path, run_id: str) -> None:
        self._path = out_path
        self._file = out_path.open("w", encoding="utf-8", newline="\n")
        self._run_id = run_id
        self._seq = 0

    def append(
        self,
        *,
        ts_utc: str,
        timeframe: str,
        risk_state: str,
        market_state: dict,
        selection: dict,
    ) -> None:
        record = {
            "schema_version": "dr.v1",
            "run_id": self._run_id,
            "seq": self._seq,
            "ts_utc": ts_utc,
            "timeframe": timeframe,
            "risk_state": risk_state,
            "market_state": market_state,
            "market_state_hash": compute_market_state_hash(market_state),
            "selection": selection,
        }
        validate_decision_record_v1(record)
        self._file.write(canonical_json(record) + "\n")
        self._file.flush()
        self._seq += 1

    def close(self) -> None:
        self._file.close()


def run_backtest(
    df_ohlcv: pd.DataFrame,
    initial_equity: float,
    *,
    run_id: str = "backtest",
    out_dir: str | Path = "runs",
    end_at_utc: str | None = None,
    commission_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> BacktestResult:
    df = _validate_ohlcv(df_ohlcv)
    if len(df) < 2:
        raise ValueError("backtest_insufficient_bars")
    if not isinstance(initial_equity, (int, float)) or initial_equity <= 0:
        raise ValueError("backtest_invalid_equity")
    if (
        not isinstance(commission_bps, (int, float))
        or isinstance(commission_bps, bool)
        or float(commission_bps) < 0.0
    ):
        raise ValueError("backtest_invalid_commission_bps")
    if (
        not isinstance(slippage_bps, (int, float))
        or isinstance(slippage_bps, bool)
        or float(slippage_bps) < 0.0
    ):
        raise ValueError("backtest_invalid_slippage_bps")

    instrument = str(df.attrs.get("instrument") or "TEST")
    features_df = _feature_frame(df)
    features_df.attrs["instrument"] = instrument
    market_state = _market_state(df)
    bundle_fingerprint = _bundle_fingerprint(df)

    pnl_method = "mark_to_market"
    end_of_run_position_handling = "close_on_end"
    strategy_switch_policy = "no_forced_flat_on_switch"

    def _apply_slippage(price: float, *, side: str) -> tuple[float, float]:
        bps = float(slippage_bps)
        if bps == 0.0:
            return price, 0.0
        mult = 1.0 + (bps / 10_000.0) if side == "BUY" else 1.0 - (bps / 10_000.0)
        effective = float(price) * mult
        slip_cost = abs(effective - float(price))
        return effective, slip_cost

    def _commission_cost(*, qty: float, price: float) -> float:
        bps = float(commission_bps)
        if bps == 0.0:
            return 0.0
        notional = abs(float(qty) * float(price))
        return notional * (bps / 10_000.0)

    run_path = Path(out_dir) / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    decision_path = run_path / "decision_records.jsonl"
    writer = _DecisionRecordsWriter(out_path=decision_path, run_id=run_id)

    equity = float(initial_equity)
    equity_curve = [equity]
    trades: list[dict[str, object]] = []
    trade_pnls: list[float] = []
    position_qty = 0.0
    entry_price = 0.0
    position_commission_paid = 0.0
    stop_loss = None
    take_profit = None
    total_costs = 0.0
    costs_breakdown = {"commission": 0.0, "slippage": 0.0}

    metadata: dict[str, Any] = {
        "bundle_fingerprint": bundle_fingerprint,
        "instrument": instrument,
        "features": _feature_metadata(),
    }

    config: dict[str, object] = {
        "execution_timing": "next_open",
        "stop_takeprofit_policy": "stop_first_if_both_touched",
        "costs": {"commission_bps": float(commission_bps), "slippage_bps": float(slippage_bps)},
        "run_id": run_id,
        "end_at_utc": end_at_utc,
        "initial_equity": initial_equity,
    }

    index = df.index
    sim_end_idx = len(df) - 1
    if end_at_utc is not None:
        cutoff = pd.to_datetime(end_at_utc, utc=True)
        sim_end_idx = int(index.searchsorted(cutoff, side="right") - 1)
        if sim_end_idx < 1:
            raise ValueError("backtest_end_before_start")
    decision_indices = list(range(sim_end_idx))

    for i in decision_indices:
        as_of_ts = index[i]
        next_ts = index[i + 1]
        as_of_utc = _iso_utc(as_of_ts)
        next_open = float(df.iloc[i + 1]["open"])
        next_high = float(df.iloc[i + 1]["high"])
        next_low = float(df.iloc[i + 1]["low"])
        next_close = float(df.iloc[i + 1]["close"])

        state_row = market_state.loc[as_of_ts]
        market_state_row = {
            "trend_state": str(state_row.get("trend_state", "unknown")),
            "momentum_state": str(state_row.get("momentum_state", "unknown")),
            "volatility_regime": str(state_row.get("volatility_regime", "unknown")),
            "structure_state": str(state_row.get("structure_state", "unknown")),
        }

        selection = select_strategy(market_state_row, RiskState.GREEN)
        selection_record = selection_to_record(selection)
        selection_record["strategy_id"] = selection.strategy_id
        selection_record["as_of_utc"] = as_of_utc

        decision = None
        strategy_version: str | None = None
        if selection.strategy_id is not None:
            registry_id = _resolve_strategy_id(selection.strategy_id)
            if registry_id is not None:
                strategy = get_strategy(registry_id)
                try:
                    decision = run_strategy(strategy, features_df, metadata, as_of_utc)
                except Exception as exc:
                    selection_record["error"] = str(exc)
                    decision = None
                if decision is not None:
                    strategy_version = str(strategy.spec.version)
                    selection_record["strategy_version"] = strategy_version
                    selection_record["decision_action"] = decision.action.value
                    selection_record["provenance"] = decision.provenance.to_dict()
                    selection_record["resolved_strategy_id"] = registry_id

        writer.append(
            ts_utc=as_of_utc,
            timeframe="1m",
            risk_state=RiskState.GREEN.value,
            market_state=market_state_row,
            selection=selection_record,
        )

        action = decision.action.value if decision is not None else "HOLD"
        if action == "ENTER_LONG" and position_qty == 0.0:
            qty = float(decision.risk.max_position_size)
            entry_price, slip_cost = _apply_slippage(next_open, side="BUY")
            position_qty = qty
            position_commission_paid = 0.0
            stop_loss = float(decision.risk.stop_loss)
            take_profit = float(decision.risk.take_profit)
            entry_comm = _commission_cost(qty=qty, price=entry_price)
            equity -= entry_comm
            position_commission_paid += entry_comm
            total_costs += entry_comm + (abs(qty) * slip_cost)
            costs_breakdown["commission"] += entry_comm
            costs_breakdown["slippage"] += abs(qty) * slip_cost
            trades.append(
                {
                    "ts_utc": _iso_utc(next_ts),
                    "side": "BUY",
                    "qty": qty,
                    "price": entry_price,
                    "price_raw": next_open,
                    "commission": entry_comm,
                    "slippage": abs(qty) * slip_cost,
                    "reason": "enter_long",
                    "pnl": 0.0,
                    "equity_after": equity,
                }
            )
            if stop_loss is not None and take_profit is not None:
                stop_hit = next_low <= stop_loss
                take_hit = next_high >= take_profit
                if stop_hit:
                    exit_price = stop_loss
                elif take_hit:
                    exit_price = take_profit
                else:
                    exit_price = None
                if exit_price is not None:
                    exit_price_eff, slip_exit = _apply_slippage(float(exit_price), side="SELL")
                    exit_comm = _commission_cost(qty=position_qty, price=exit_price_eff)
                    equity -= exit_comm
                    gross = (exit_price_eff - entry_price) * position_qty
                    equity += gross
                    net = gross - position_commission_paid - exit_comm
                    trades.append(
                        {
                            "ts_utc": _iso_utc(next_ts),
                            "side": "SELL",
                            "qty": position_qty,
                            "price": exit_price_eff,
                            "price_raw": float(exit_price),
                            "commission": exit_comm,
                            "slippage": abs(position_qty) * slip_exit,
                            "reason": "stop_loss" if stop_hit else "take_profit",
                            "pnl": net,
                            "equity_after": equity,
                        }
                    )
                    total_costs += exit_comm + (abs(position_qty) * slip_exit)
                    costs_breakdown["commission"] += exit_comm
                    costs_breakdown["slippage"] += abs(position_qty) * slip_exit
                    trade_pnls.append(net)
                    position_qty = 0.0
                    entry_price = 0.0
                    position_commission_paid = 0.0
                    stop_loss = None
                    take_profit = None
        elif action == "EXIT_LONG" and position_qty > 0.0:
            exit_price_eff, slip_exit = _apply_slippage(next_open, side="SELL")
            exit_comm = _commission_cost(qty=position_qty, price=exit_price_eff)
            equity -= exit_comm
            gross = (exit_price_eff - entry_price) * position_qty
            equity += gross
            net = gross - position_commission_paid - exit_comm
            trades.append(
                {
                    "ts_utc": _iso_utc(next_ts),
                    "side": "SELL",
                    "qty": position_qty,
                    "price": exit_price_eff,
                    "price_raw": next_open,
                    "commission": exit_comm,
                    "slippage": abs(position_qty) * slip_exit,
                    "reason": "exit_long",
                    "pnl": net,
                    "equity_after": equity,
                }
            )
            total_costs += exit_comm + (abs(position_qty) * slip_exit)
            costs_breakdown["commission"] += exit_comm
            costs_breakdown["slippage"] += abs(position_qty) * slip_exit
            trade_pnls.append(net)
            position_qty = 0.0
            entry_price = 0.0
            position_commission_paid = 0.0
            stop_loss = None
            take_profit = None
        elif position_qty > 0.0 and stop_loss is not None and take_profit is not None:
            stop_hit = next_low <= stop_loss
            take_hit = next_high >= take_profit
            if stop_hit or take_hit:
                exit_price = stop_loss if stop_hit else take_profit
                exit_price_eff, slip_exit = _apply_slippage(float(exit_price), side="SELL")
                exit_comm = _commission_cost(qty=position_qty, price=exit_price_eff)
                equity -= exit_comm
                gross = (exit_price_eff - entry_price) * position_qty
                equity += gross
                net = gross - position_commission_paid - exit_comm
                trades.append(
                    {
                        "ts_utc": _iso_utc(next_ts),
                        "side": "SELL",
                        "qty": position_qty,
                        "price": exit_price_eff,
                        "price_raw": float(exit_price),
                        "commission": exit_comm,
                        "slippage": abs(position_qty) * slip_exit,
                        "reason": "stop_loss" if stop_hit else "take_profit",
                        "pnl": net,
                        "equity_after": equity,
                    }
                )
                total_costs += exit_comm + (abs(position_qty) * slip_exit)
                costs_breakdown["commission"] += exit_comm
                costs_breakdown["slippage"] += abs(position_qty) * slip_exit
                trade_pnls.append(net)
                position_qty = 0.0
                entry_price = 0.0
                position_commission_paid = 0.0
                stop_loss = None
                take_profit = None

        if pnl_method == "mark_to_market" and position_qty > 0.0:
            equity_curve.append(equity + (next_close - entry_price) * position_qty)
        else:
            equity_curve.append(equity)

    writer.close()

    if end_of_run_position_handling == "close_on_end" and position_qty > 0.0:
        end_ts = index[sim_end_idx]
        end_close = float(df.iloc[sim_end_idx]["close"])
        exit_price_eff, slip_exit = _apply_slippage(end_close, side="SELL")
        exit_comm = _commission_cost(qty=position_qty, price=exit_price_eff)
        equity -= exit_comm
        gross = (exit_price_eff - entry_price) * position_qty
        equity += gross
        net = gross - position_commission_paid - exit_comm
        trades.append(
            {
                "ts_utc": _iso_utc(end_ts),
                "side": "SELL",
                "qty": position_qty,
                "price": exit_price_eff,
                "price_raw": end_close,
                "commission": exit_comm,
                "slippage": abs(position_qty) * slip_exit,
                "reason": "close_on_end",
                "pnl": net,
                "equity_after": equity,
            }
        )
        total_costs += exit_comm + (abs(position_qty) * slip_exit)
        costs_breakdown["commission"] += exit_comm
        costs_breakdown["slippage"] += abs(position_qty) * slip_exit
        trade_pnls.append(net)
        position_qty = 0.0
        entry_price = 0.0
        position_commission_paid = 0.0
        stop_loss = None
        take_profit = None
        equity_curve[-1] = equity

    trades_path = run_path / "trades.parquet"
    metrics_path = run_path / "metrics.json"
    decision_records_path = decision_path
    _write_trades(trades_path, trades)

    metrics = _metrics_from_equity(equity_curve, trade_pnls)
    metrics_payload = dict(metrics)
    metrics_payload["config"] = config
    metrics_payload["pnl_method"] = pnl_method
    metrics_payload["end_of_run_position_handling"] = end_of_run_position_handling
    metrics_payload["strategy_switch_policy"] = strategy_switch_policy
    metrics_payload["total_costs"] = float(total_costs)
    metrics_payload["costs_breakdown"] = {
        "commission": float(costs_breakdown["commission"]),
        "slippage": float(costs_breakdown["slippage"]),
    }
    _write_json(metrics_path, metrics_payload)

    manifest_path = run_path / "run_manifest.json"
    manifest_payload: dict[str, object] = {
        "run_id": run_id,
        "git_sha": _git_sha(),
        "config": config,
        "pnl_method": pnl_method,
        "end_of_run_position_handling": end_of_run_position_handling,
        "strategy_switch_policy": strategy_switch_policy,
        "data_start_utc": _iso_utc(index[0]),
        "data_end_utc": _iso_utc(index[-1]),
        "artifacts": {
            "trades": str(trades_path),
            "metrics": str(metrics_path),
            "decision_records": str(decision_records_path),
        },
    }
    _write_json(manifest_path, manifest_payload)

    return BacktestResult(
        trades=pd.DataFrame(trades),
        metrics=metrics,
        trades_path=trades_path,
        metrics_path=metrics_path,
        decision_records_path=decision_records_path,
        manifest_path=manifest_path,
    )
