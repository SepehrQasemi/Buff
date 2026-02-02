from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping


_ALLOWED_ACTIONS = {"allow", "blocked", "no_trade"}
_ORDER_SIDES = {"buy", "sell"}
_ORDER_TYPES = {"market", "limit"}


@dataclass(frozen=True)
class DecisionValidationError(RuntimeError):
    reason: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.reason


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def inputs_digest(payload: Mapping[str, Any]) -> str:
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _normalize_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _key(item: dict[str, Any]) -> tuple:
        return (
            str(item.get("symbol", "")),
            str(item.get("side", "")),
            float(item.get("qty", 0.0)),
            str(item.get("order_type", "")),
            item.get("limit_price") if item.get("limit_price") is not None else -1.0,
        )

    return sorted(orders, key=_key)


def validate_decision_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise DecisionValidationError("invalid_decision_schema")

    action = payload.get("action")
    if action not in _ALLOWED_ACTIONS:
        raise DecisionValidationError("invalid_action")

    reason = payload.get("reason")
    if not isinstance(reason, str):
        raise DecisionValidationError("invalid_reason")
    if action == "blocked" and not reason:
        raise DecisionValidationError("missing_block_reason")

    strategy_id = payload.get("strategy_id")
    if not isinstance(strategy_id, str) or not strategy_id:
        raise DecisionValidationError("invalid_strategy_id")

    strategy_version = payload.get("strategy_version")
    if not isinstance(strategy_version, int) or isinstance(strategy_version, bool):
        raise DecisionValidationError("invalid_strategy_version")

    step_id = payload.get("step_id")
    if not isinstance(step_id, (str, int)) or step_id == "":
        raise DecisionValidationError("invalid_step_id")

    digest = payload.get("inputs_digest")
    if not isinstance(digest, str) or not digest:
        raise DecisionValidationError("invalid_inputs_digest")

    orders = payload.get("orders")
    if not isinstance(orders, list):
        raise DecisionValidationError("invalid_orders")

    for order in orders:
        if not isinstance(order, Mapping):
            raise DecisionValidationError("invalid_order")
        symbol = order.get("symbol")
        side = order.get("side")
        qty = order.get("qty")
        order_type = order.get("order_type")
        limit_price = order.get("limit_price")

        if not isinstance(symbol, str) or not symbol:
            raise DecisionValidationError("invalid_order_symbol")
        if side not in _ORDER_SIDES:
            raise DecisionValidationError("invalid_order_side")
        if not isinstance(qty, (int, float)) or float(qty) <= 0.0:
            raise DecisionValidationError("invalid_order_qty")
        if order_type not in _ORDER_TYPES:
            raise DecisionValidationError("invalid_order_type")
        if order_type == "limit":
            if not isinstance(limit_price, (int, float)) or float(limit_price) <= 0.0:
                raise DecisionValidationError("invalid_limit_price")
        else:
            if limit_price is not None:
                raise DecisionValidationError("invalid_limit_price")


def build_decision_payload(
    *,
    action: str,
    reason: str,
    strategy_id: str,
    strategy_version: int,
    step_id: str | int,
    inputs_payload: Mapping[str, Any],
    orders: list[dict[str, Any]],
) -> dict[str, Any]:
    digest = inputs_digest(inputs_payload)
    normalized_orders = _normalize_orders(list(orders))
    payload = {
        "action": action,
        "reason": reason,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "step_id": step_id,
        "inputs_digest": digest,
        "orders": normalized_orders,
    }
    validate_decision_payload(payload)
    return payload
