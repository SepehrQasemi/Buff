"""Paper order intent model (deterministic, serializable)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Any, Mapping
import uuid

import hashlib
import json


class OrderSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    created_at_utc: str
    symbol: str
    side: OrderSide
    qty: float
    order_type: OrderType
    limit_price: float | None
    reduce_only: bool = False
    client_tag: str = "paper"
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "created_at_utc": self.created_at_utc,
            "symbol": self.symbol,
            "side": self.side.value,
            "qty": self.qty,
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "reduce_only": self.reduce_only,
            "client_tag": self.client_tag,
            "metadata": dict(self.metadata),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    def intent_hash(self) -> str:
        payload = {
            "symbol": self.symbol,
            "side": self.side.value,
            "qty": self.qty,
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "reduce_only": self.reduce_only,
            "client_tag": self.client_tag,
            "metadata": dict(self.metadata),
        }
        return _sha256_hex(_canonical_json(payload))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OrderIntent":
        if not isinstance(payload, Mapping):
            raise ValueError("intent_payload_invalid")
        intent = cls(
            intent_id=str(payload.get("intent_id") or uuid.uuid4()),
            created_at_utc=str(payload.get("created_at_utc") or _utc_now_z()),
            symbol=str(payload.get("symbol") or ""),
            side=_parse_side(payload.get("side")),
            qty=float(payload.get("qty")) if payload.get("qty") is not None else float("nan"),
            order_type=_parse_order_type(payload.get("order_type")),
            limit_price=_parse_optional_float(payload.get("limit_price")),
            reduce_only=bool(payload.get("reduce_only", False)),
            client_tag=str(payload.get("client_tag") or "paper"),
            metadata=_parse_metadata(payload.get("metadata")),
        )
        validate_intent(intent)
        return intent


def _utc_now_z() -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return ts.replace("+00:00", "Z")


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_side(value: Any) -> OrderSide:
    if isinstance(value, OrderSide):
        return value
    if isinstance(value, str):
        try:
            return OrderSide(value.upper())
        except ValueError as exc:
            raise ValueError("side_invalid") from exc
    raise ValueError("side_invalid")


def _parse_order_type(value: Any) -> OrderType:
    if isinstance(value, OrderType):
        return value
    if isinstance(value, str):
        try:
            return OrderType(value.upper())
        except ValueError as exc:
            raise ValueError("order_type_invalid") from exc
    raise ValueError("order_type_invalid")


def _parse_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise ValueError("limit_price_invalid")
    value = float(value)
    if not isfinite(value):
        raise ValueError("limit_price_invalid")
    return value


def _parse_metadata(value: Any) -> Mapping[str, str]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return {str(k): str(v) for k, v in value.items()}
    raise ValueError("metadata_invalid")


def _validate_timestamp(ts: str) -> None:
    if not ts or not isinstance(ts, str):
        raise ValueError("created_at_utc_invalid")
    if not ts.endswith("Z"):
        raise ValueError("created_at_utc_invalid")
    try:
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("created_at_utc_invalid") from exc


def validate_intent(intent: OrderIntent) -> None:
    if not isinstance(intent, OrderIntent):
        raise ValueError("intent_invalid")
    if not intent.symbol or not intent.symbol.strip():
        raise ValueError("symbol_invalid")
    if not isinstance(intent.qty, (int, float)) or not isfinite(float(intent.qty)):
        raise ValueError("qty_invalid")
    if float(intent.qty) <= 0.0:
        raise ValueError("qty_invalid")
    if not isinstance(intent.side, OrderSide):
        raise ValueError("side_invalid")
    if not isinstance(intent.order_type, OrderType):
        raise ValueError("order_type_invalid")
    _validate_timestamp(intent.created_at_utc)

    if intent.order_type is OrderType.LIMIT:
        if intent.limit_price is None or not isfinite(float(intent.limit_price)):
            raise ValueError("limit_price_invalid")
        if float(intent.limit_price) <= 0.0:
            raise ValueError("limit_price_invalid")
    else:
        if intent.limit_price is not None:
            raise ValueError("limit_price_invalid")
