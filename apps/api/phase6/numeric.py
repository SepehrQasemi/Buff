from __future__ import annotations

import math
from dataclasses import is_dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

try:
    import numpy as np
except Exception:  # pragma: no cover - optional
    np = None  # type: ignore

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional
    pd = None  # type: ignore

# Numeric policy: round floats to 8 decimal places (HALF_UP) before serialization.
_FLOAT_QUANT = Decimal("0.00000001")


class NonFiniteNumberError(ValueError):
    pass


def _quantize_decimal(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise NonFiniteNumberError("non_finite_decimal")
    if value == 0:
        value = Decimal("0")
    return value.quantize(_FLOAT_QUANT, rounding=ROUND_HALF_UP)


def _normalize_float(value: float) -> Decimal:
    if not math.isfinite(value):
        raise NonFiniteNumberError("non_finite_float")
    return _quantize_decimal(Decimal(str(value)))


def normalize_numbers(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        return _normalize_float(value)
    if isinstance(value, Decimal):
        return _quantize_decimal(value)

    if np is not None:
        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return _normalize_float(float(value))

    if pd is not None:
        if isinstance(value, pd.Timestamp):
            dt = value.to_pydatetime()
            return dt.isoformat()

    if isinstance(value, datetime):
        return value.isoformat()

    if is_dataclass(value):
        return normalize_numbers(value.__dict__)

    if isinstance(value, (list, tuple)):
        return [normalize_numbers(item) for item in value]

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical_json keys must be strings")
            normalized[key] = normalize_numbers(item)
        return normalized

    raise TypeError(f"Unsupported type for numeric normalization: {type(value).__name__}")
