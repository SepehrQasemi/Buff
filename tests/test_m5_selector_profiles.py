from __future__ import annotations

from selector.selector import select_strategy


def test_red_veto() -> None:
    result = select_strategy(market_state={"trend_state": "UP"}, risk_state="RED", timeframe="1h")
    assert result["strategy_id"] == "NONE"
    assert "RISK_VETO:RED" in result["reason"]


def test_green_select_trend_conservative_up() -> None:
    result = select_strategy(market_state={"trend_state": "UP"}, risk_state="GREEN", timeframe="1h")
    assert result["strategy_id"] == "trend_follow_v1_conservative"
    assert any(reason.startswith("SELECTED:") for reason in result["reason"])


def test_yellow_only_conservative() -> None:
    result = select_strategy(market_state={"trend_state": "DOWN"}, risk_state="YELLOW", timeframe="1h")
    assert result["strategy_id"] == "NONE"
    assert "RISK_LIMIT:YELLOW" in result["reason"]


def test_missing_keys_returns_none() -> None:
    result = select_strategy(market_state={}, risk_state="GREEN", timeframe="1h")
    assert result["strategy_id"] == "NONE"
    assert "NO_APPLICABLE_STRATEGY" in result["reason"]


def test_deterministic_repeatability() -> None:
    market_state = {"trend_state": "RANGE", "volatility_regime": "LOW"}
    result_a = select_strategy(market_state=market_state, risk_state="GREEN", timeframe="1h")
    result_b = select_strategy(market_state=market_state, risk_state="GREEN", timeframe="1h")
    assert result_a == result_b
