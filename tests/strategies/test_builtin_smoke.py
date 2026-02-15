from __future__ import annotations

from strategies.builtins.harness import run_intent_backtest
from strategies.registry import get_strategy, list_strategies

from tests.strategies.helpers import synthetic_ohlcv


def _wrapper_params(strategy_id: str) -> dict[str, float | int]:
    if strategy_id == "time_based_exit_wrapper":
        return {"max_bars": 5}
    if strategy_id == "trailing_stop_wrapper":
        return {"trail_pct": 0.01}
    if strategy_id == "fixed_rr_stop_target_wrapper":
        return {"stop_pct": 0.01, "reward_ratio": 1.5}
    return {}


def test_builtin_strategies_smoke_artifacts() -> None:
    ohlcv = synthetic_ohlcv(100)
    for schema in list_strategies():
        strategy = get_strategy(f"{schema['id']}@{schema['version']}")
        initial_position = None
        params = _wrapper_params(schema["id"])
        if schema["category"] == "wrapper":
            initial_position = {
                "side": "LONG",
                "entry_price": float(ohlcv["close"].iloc[0]),
                "entry_index": 0,
                "max_price": float(ohlcv["high"].iloc[0]),
                "min_price": float(ohlcv["low"].iloc[0]),
                "bars_in_trade": 0,
            }
        artifacts = run_intent_backtest(
            strategy,
            ohlcv,
            params=params,
            initial_position=initial_position,
        )
        assert isinstance(artifacts.trades, list)
        assert isinstance(artifacts.metrics, dict)
        assert isinstance(artifacts.timeline, list)
        assert artifacts.timeline
        assert "num_trades" in artifacts.metrics
