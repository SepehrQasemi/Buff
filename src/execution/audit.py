from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class DecisionRecord:
    record_version: int
    decision_id: str
    timestamp: str
    event_id: str
    intent_id: str
    strategy_id: str
    risk_state: str
    permission: str
    action: str
    reason: str
    data_snapshot_hash: str
    feature_snapshot_hash: str
    execution: Mapping[str, object]
    notes: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


class DecisionWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: DecisionRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.to_json())
            handle.write("\n")
