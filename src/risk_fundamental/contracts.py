"""Contracts and validation helpers for fundamental risk snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Evidence:
    rule_id: str
    domain: str
    matched: bool
    severity: float
    inputs_used: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class FundamentalSnapshot:
    timestamp: datetime
    macro: dict[str, Any]
    onchain: dict[str, Any]
    news: dict[str, Any]
    provenance: dict[str, Any] = field(default_factory=dict)


def ensure_utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp_not_timezone_aware")
    return value.astimezone(timezone.utc)


def _dtype_matches(value: Any, dtype: str, enum: list[Any] | None) -> bool:
    if value is None:
        return True
    if dtype == "float":
        return isinstance(value, (float, int)) and not isinstance(value, bool)
    if dtype == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if dtype == "str":
        return isinstance(value, str)
    if dtype == "bool":
        return isinstance(value, bool)
    return False


def validate_snapshot_against_catalog(
    snapshot: FundamentalSnapshot, inputs_catalog: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """Validate snapshot keys/types against the inputs catalog.

    Returns (missing_inputs, missing_critical_inputs).
    """

    catalog_by_domain: dict[str, dict[str, dict[str, Any]]] = {}
    for entry in inputs_catalog:
        domain = str(entry.get("domain"))
        key = str(entry.get("key"))
        catalog_by_domain.setdefault(domain, {})[key] = entry

    for domain_name, values in {
        "macro": snapshot.macro,
        "onchain": snapshot.onchain,
        "news": snapshot.news,
    }.items():
        if not isinstance(values, dict):
            raise ValueError(f"invalid_snapshot_domain:{domain_name}")
        for key, value in values.items():
            if key not in catalog_by_domain.get(domain_name, {}):
                raise ValueError(f"unknown_input_key:{domain_name}:{key}")
            entry = catalog_by_domain[domain_name][key]
            dtype = str(entry.get("dtype"))
            enum = entry.get("enum") if isinstance(entry.get("enum"), list) else None
            if not _dtype_matches(value, dtype, enum):
                raise ValueError(f"invalid_input_type:{key}")
            if enum is not None and value is not None and value not in enum:
                raise ValueError(f"invalid_input_enum:{key}")

    missing: list[str] = []
    missing_critical: list[str] = []
    for domain, entries in catalog_by_domain.items():
        values = getattr(snapshot, domain, {})
        for key, entry in entries.items():
            if key not in values or values.get(key) is None:
                missing.append(key)
                if bool(entry.get("critical")):
                    missing_critical.append(key)

    return sorted(set(missing)), sorted(set(missing_critical))
