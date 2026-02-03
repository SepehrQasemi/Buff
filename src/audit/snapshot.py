from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from audit.canonical_json import canonical_json_bytes


def _sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    return value


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a dict")
    for key in value.keys():
        if not isinstance(key, str):
            raise ValueError(f"{field} keys must be strings")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


@dataclass(frozen=True)
class Snapshot:
    snapshot_version: int
    decision_id: str
    symbol: str
    timeframe: str
    market_data: list[dict[str, Any]] | None
    features: dict[str, Any] | None
    risk_inputs: dict[str, Any] | None
    config: dict[str, Any] | None
    selector_inputs: dict[str, Any] | None
    snapshot_hash: str | None = None

    def __post_init__(self) -> None:
        _require_int(self.snapshot_version, "snapshot_version")
        _require_str(self.decision_id, "decision_id")
        _require_str(self.symbol, "symbol")
        _require_str(self.timeframe, "timeframe")
        if self.market_data is not None:
            _require_list(self.market_data, "market_data")
            for idx, row in enumerate(self.market_data):
                _require_dict(row, f"market_data[{idx}]")
        if self.features is not None:
            _require_dict(self.features, "features")
        if self.risk_inputs is not None:
            _require_dict(self.risk_inputs, "risk_inputs")
        if self.config is not None:
            _require_dict(self.config, "config")
        if self.selector_inputs is not None:
            _require_dict(self.selector_inputs, "selector_inputs")

        computed = self._compute_hash()
        if self.snapshot_hash is None:
            object.__setattr__(self, "snapshot_hash", computed)
        elif self.snapshot_hash != computed:
            raise ValueError("snapshot_hash does not match computed value")

    def _payload_without_hash(self) -> dict[str, Any]:
        return {
            "snapshot_version": self.snapshot_version,
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "market_data": self.market_data,
            "features": self.features,
            "risk_inputs": self.risk_inputs,
            "config": self.config,
            "selector_inputs": self.selector_inputs,
        }

    def _compute_hash(self) -> str:
        payload = self._payload_without_hash()
        return _sha256_hex(canonical_json_bytes(payload))

    def _to_payload(self, *, snapshot_hash: str) -> dict[str, Any]:
        payload = self._payload_without_hash()
        payload["snapshot_hash"] = snapshot_hash
        return payload

    def to_dict(self) -> dict[str, Any]:
        snapshot_hash = self.snapshot_hash or self._compute_hash()
        return self._to_payload(snapshot_hash=snapshot_hash)

    def to_canonical_json(self) -> str:
        return canonical_json_bytes(self.to_dict()).decode("utf-8")

    @property
    def snapshot_ref(self) -> str:
        snapshot_hash = self.snapshot_hash or self._compute_hash()
        return f"snapshot_{snapshot_hash}.json"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Snapshot":
        if not isinstance(payload, Mapping):
            raise ValueError("snapshot payload must be a mapping")
        return cls(
            snapshot_version=payload.get("snapshot_version", 1),
            decision_id=payload.get("decision_id"),
            symbol=payload.get("symbol"),
            timeframe=payload.get("timeframe"),
            market_data=payload.get("market_data"),
            features=payload.get("features"),
            risk_inputs=payload.get("risk_inputs"),
            config=payload.get("config"),
            selector_inputs=payload.get("selector_inputs"),
            snapshot_hash=payload.get("snapshot_hash"),
        )


def create_snapshot(payload: Mapping[str, Any], out_dir: str | Path) -> Path:
    snapshot = Snapshot.from_dict(payload)
    out_path = Path(out_dir) / snapshot.snapshot_ref
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(snapshot.to_canonical_json(), encoding="utf-8")
    return out_path


def load_snapshot(path: str | Path) -> Snapshot:
    raw = Path(path).read_text(encoding="utf-8")
    payload = json_loads(raw)
    return Snapshot.from_dict(payload)


def json_loads(raw: str) -> dict[str, Any]:
    import json

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("snapshot must be a JSON object")
    return data
