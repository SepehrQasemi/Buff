from __future__ import annotations

import json
import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

_FLOAT_QUANT = Decimal("0.00000001")


def _format_decimal(value: Decimal, path: str) -> str:
    if not value.is_finite():
        raise ValueError(f"Non-finite decimal at {path}")
    if value == 0:
        value = Decimal("0")
    quantized = value.quantize(_FLOAT_QUANT, rounding=ROUND_HALF_UP)
    return format(quantized, "f")


def _format_float(value: float, path: str) -> str:
    if not math.isfinite(value):
        raise ValueError(f"Non-finite float at {path}")
    if value == 0.0:
        value = 0.0
    return _format_decimal(Decimal(str(value)), path)


def _serialize(value: Any, path: str) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return _format_float(value, path)
    if isinstance(value, Decimal):
        return _format_decimal(value, path)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        items = []
        for idx, item in enumerate(value):
            items.append(_serialize(item, f"{path}[{idx}]"))
        return "[" + ",".join(items) + "]"
    if isinstance(value, dict):
        items: list[str] = []
        for key in sorted(value.keys()):
            if not isinstance(key, str):
                raise TypeError(f"canonical_json keys must be strings at {path}")
            next_path = f"{path}.{key}" if path else key
            items.append(
                f"{json.dumps(key, ensure_ascii=False)}:{_serialize(value[key], next_path)}"
            )
        return "{" + ",".join(items) + "}"
    raise TypeError(f"Unsupported type for canonical_json: {type(value).__name__}")


def canonical_json(obj: Any) -> str:
    return _serialize(obj, "$")


def canonical_json_bytes(obj: Any) -> bytes:
    return canonical_json(obj).encode("utf-8")
