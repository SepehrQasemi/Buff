"""Offline snapshot provider that reads from a JSON fixture."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import SnapshotProvider
from ..contracts import FundamentalSnapshot, ensure_utc_timestamp


def _parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


class OfflineSnapshotProvider(SnapshotProvider):
    def __init__(self, fixture_path: str | Path) -> None:
        self._path = Path(fixture_path)
        self._snapshots = self._load_snapshots()

    def _load_snapshots(self) -> list[FundamentalSnapshot]:
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("fixture_not_list")
        snapshots: list[FundamentalSnapshot] = []
        for entry in payload:
            if not isinstance(entry, dict):
                raise ValueError("fixture_entry_invalid")
            ts_raw = entry.get("timestamp")
            if not isinstance(ts_raw, str):
                raise ValueError("fixture_timestamp_invalid")
            timestamp = _parse_timestamp(ts_raw)
            timestamp = ensure_utc_timestamp(timestamp)
            snapshots.append(
                FundamentalSnapshot(
                    timestamp=timestamp,
                    macro=dict(entry.get("macro") or {}),
                    onchain=dict(entry.get("onchain") or {}),
                    news=dict(entry.get("news") or {}),
                    provenance=dict(entry.get("provenance") or {}),
                )
            )
        return sorted(snapshots, key=lambda s: s.timestamp)

    def list_snapshots(self) -> list[FundamentalSnapshot]:
        return list(self._snapshots)

    def get_snapshot(self, at: datetime) -> FundamentalSnapshot:
        at_utc = ensure_utc_timestamp(at)
        for snapshot in self._snapshots:
            if snapshot.timestamp == at_utc:
                return snapshot
        raise ValueError("snapshot_not_found")


def snapshot_from_dict(data: dict[str, Any]) -> FundamentalSnapshot:
    ts_raw = data.get("timestamp")
    if not isinstance(ts_raw, str):
        raise ValueError("snapshot_timestamp_invalid")
    timestamp = _parse_timestamp(ts_raw)
    timestamp = ensure_utc_timestamp(timestamp)
    return FundamentalSnapshot(
        timestamp=timestamp,
        macro=dict(data.get("macro") or {}),
        onchain=dict(data.get("onchain") or {}),
        news=dict(data.get("news") or {}),
        provenance=dict(data.get("provenance") or {}),
    )
