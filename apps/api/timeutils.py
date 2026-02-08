from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .errors import raise_api_error


def parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError("timestamp is empty")
        if raw.isdigit():
            dt = datetime.fromtimestamp(int(raw) / 1000.0, tz=timezone.utc)
        else:
            if raw.endswith("Z"):
                raw = f"{raw[:-1]}+00:00"
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError as exc:
                raise ValueError("invalid ISO-8601 timestamp") from exc
    else:
        raise ValueError("unsupported timestamp type")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_ts(value: datetime | None) -> str | None:
    if value is None:
        return None
    dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    formatted = dt.isoformat(timespec="milliseconds")
    if formatted.endswith("+00:00"):
        formatted = f"{formatted[:-6]}Z"
    return formatted


def coerce_ts_param(value: Any, param_name: str) -> datetime | None:
    if value is None:
        return None
    try:
        return parse_ts(value)
    except ValueError as exc:
        raise_api_error(
            400,
            "invalid_timestamp",
            f"Invalid {param_name}: {exc}",
            {"param": param_name, "value": value},
        )
        return None
