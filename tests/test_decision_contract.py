from __future__ import annotations

from execution.decision_contract import build_decision_payload, canonical_json


def test_decision_json_is_deterministic() -> None:
    inputs_payload = {
        "strategy_id": "strat-1",
        "strategy_version": 1,
        "step_id": "step-1",
        "data_snapshot_hash": "data",
        "feature_snapshot_hash": "features",
        "risk_state": "GREEN",
        "permission": "ALLOW",
        "current_exposure": 0.0,
        "trades_today": 0,
    }
    orders = [
        {
            "symbol": "ETHUSDT",
            "side": "sell",
            "qty": 2.0,
            "order_type": "market",
            "limit_price": None,
        },
        {
            "symbol": "BTCUSDT",
            "side": "buy",
            "qty": 1.0,
            "order_type": "market",
            "limit_price": None,
        },
    ]
    payload_a = build_decision_payload(
        action="allow",
        reason="ok",
        strategy_id="strat-1",
        strategy_version=1,
        step_id="step-1",
        inputs_payload=inputs_payload,
        orders=orders,
    )
    payload_b = build_decision_payload(
        action="allow",
        reason="ok",
        strategy_id="strat-1",
        strategy_version=1,
        step_id="step-1",
        inputs_payload=inputs_payload,
        orders=orders,
    )
    assert canonical_json(payload_a) == canonical_json(payload_b)


def test_orders_sorted_deterministically() -> None:
    inputs_payload = {
        "strategy_id": "strat-1",
        "strategy_version": 1,
        "step_id": "step-1",
        "data_snapshot_hash": "data",
        "feature_snapshot_hash": "features",
        "risk_state": "GREEN",
        "permission": "ALLOW",
        "current_exposure": 0.0,
        "trades_today": 0,
    }
    orders = [
        {
            "symbol": "ETHUSDT",
            "side": "sell",
            "qty": 2.0,
            "order_type": "market",
            "limit_price": None,
        },
        {
            "symbol": "BTCUSDT",
            "side": "buy",
            "qty": 1.0,
            "order_type": "market",
            "limit_price": None,
        },
    ]
    payload = build_decision_payload(
        action="allow",
        reason="ok",
        strategy_id="strat-1",
        strategy_version=1,
        step_id="step-1",
        inputs_payload=inputs_payload,
        orders=orders,
    )
    assert [order["symbol"] for order in payload["orders"]] == ["BTCUSDT", "ETHUSDT"]
