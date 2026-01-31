"""Tests for paper order intent model."""

from __future__ import annotations

from math import nan

import pytest

from execution.intent import OrderIntent, OrderSide, OrderType, validate_intent


pytestmark = pytest.mark.unit


def _base_intent() -> OrderIntent:
    return OrderIntent(
        intent_id="intent-1",
        created_at_utc="2024-01-01T00:00:00Z",
        symbol="BTCUSDT",
        side=OrderSide.LONG,
        qty=1.0,
        order_type=OrderType.MARKET,
        limit_price=None,
        reduce_only=False,
        client_tag="paper",
        metadata={"strategy_id": "strat-1", "timeframe": "1h"},
    )


def test_valid_market_intent() -> None:
    intent = _base_intent()
    validate_intent(intent)


def test_valid_limit_intent() -> None:
    intent = _base_intent()
    intent = OrderIntent.from_dict(
        {**intent.to_dict(), "order_type": OrderType.LIMIT.value, "limit_price": 100.0}
    )
    validate_intent(intent)


@pytest.mark.parametrize("qty", [0.0, -1.0, nan])
def test_invalid_qty(qty: float) -> None:
    intent = _base_intent()
    intent = OrderIntent(**{**intent.to_dict(), "qty": qty})
    with pytest.raises(ValueError, match="qty_invalid"):
        validate_intent(intent)


def test_invalid_limit_price_cases() -> None:
    intent = _base_intent()
    with pytest.raises(ValueError, match="limit_price_invalid"):
        OrderIntent.from_dict(
            {**intent.to_dict(), "order_type": OrderType.LIMIT.value, "limit_price": None}
        )

    intent = _base_intent()
    with pytest.raises(ValueError, match="limit_price_invalid"):
        OrderIntent.from_dict(
            {**intent.to_dict(), "order_type": OrderType.LIMIT.value, "limit_price": -1.0}
        )

    intent = _base_intent()
    with pytest.raises(ValueError, match="limit_price_invalid"):
        OrderIntent.from_dict(
            {**intent.to_dict(), "order_type": OrderType.MARKET.value, "limit_price": 10.0}
        )


def test_round_trip_and_determinism() -> None:
    intent = _base_intent()
    payload = intent.to_dict()
    rebuilt = OrderIntent.from_dict(payload)
    assert rebuilt.to_dict() == intent.to_dict()
    assert intent.canonical_json() == rebuilt.canonical_json()
    assert intent.intent_hash() == rebuilt.intent_hash()


def test_intent_hash_excludes_id_and_timestamp() -> None:
    base = _base_intent()
    first = base.intent_hash()
    altered = OrderIntent(
        intent_id="intent-2",
        created_at_utc="2024-01-01T00:01:00Z",
        symbol=base.symbol,
        side=base.side,
        qty=base.qty,
        order_type=base.order_type,
        limit_price=base.limit_price,
        reduce_only=base.reduce_only,
        client_tag=base.client_tag,
        metadata=base.metadata,
    )
    assert altered.intent_hash() == first
