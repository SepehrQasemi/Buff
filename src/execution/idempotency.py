from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from execution.types import OrderIntent


def _utc_now_z() -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return ts.replace("+00:00", "Z")


def make_idempotency_key(intent: OrderIntent, *, run_id: str | None = None) -> str:
    """Derive a stable idempotency key from intent.intent_hash and optional run scope."""

    base = intent.intent_hash()
    return f"{run_id}:{base}" if run_id else base


@dataclass
class IdempotencyStore:
    """In-memory idempotency store for dedupe protection."""

    records: dict[str, Mapping[str, Any]] = field(default_factory=dict)

    def has(self, key: str) -> bool:
        return key in self.records

    def get(self, key: str) -> Mapping[str, Any]:
        return self.records[key]

    def put(self, key: str, record: Mapping[str, Any]) -> None:
        self.records[key] = dict(record)

    def reserve_inflight(self, key: str, record: Mapping[str, Any]) -> bool:
        if key in self.records:
            return False
        self.records[key] = dict(record)
        return True

    def get_record(self, key: str) -> Mapping[str, Any]:
        return self.records[key]

    def finalize_processed(self, key: str, record: Mapping[str, Any]) -> None:
        if key not in self.records:
            raise KeyError(key)
        self.records[key] = dict(record)


def build_idempotency_record(
    *,
    status: str,
    order_id: str | None,
    audit_ref: str | None,
    decision: Mapping[str, Any],
    timestamp_utc: str | None = None,
    first_seen_utc: str | None = None,
) -> Mapping[str, Any]:
    first_seen = first_seen_utc or timestamp_utc or _utc_now_z()
    return {
        "status": status,
        "order_id": order_id,
        "timestamp_utc": timestamp_utc or _utc_now_z(),
        "first_seen_utc": first_seen,
        "audit_ref": audit_ref,
        "decision": dict(decision),
        "result": dict(decision),
    }


def build_inflight_record(*, first_seen_utc: str | None = None) -> Mapping[str, Any]:
    return {
        "status": "INFLIGHT",
        "first_seen_utc": first_seen_utc or _utc_now_z(),
        "result": None,
    }
