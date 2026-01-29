from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    digest = sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def parse_json_line(line: str) -> dict:
    return json.loads(line)


def compute_market_state_hash(market_state: dict) -> str:
    return sha256_hex(canonical_json(market_state))


@dataclass(frozen=True)
class DecisionRecordV1:
    schema_version: str
    run_id: str
    seq: int
    ts_utc: str
    timeframe: str
    risk_state: str
    market_state: dict
    market_state_hash: str
    selection: dict

    def to_json_line(self) -> str:
        return canonical_json(asdict(self)) + "\n"


def ensure_run_dir(run_id: str) -> str:
    path = Path("runs") / run_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path / "decision_records.jsonl")


def _utc_timestamp() -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    if ts.endswith("+00:00"):
        return ts.replace("+00:00", "Z")
    return ts


class DecisionRecordWriter:
    def __init__(self, *, out_path: str, run_id: str) -> None:
        self._file = open(out_path, "a", encoding="utf-8")
        self._run_id = run_id
        self._seq = 0

    def append(
        self,
        *,
        timeframe: str,
        risk_state: str,
        market_state: dict,
        selection: dict,
    ) -> DecisionRecordV1:
        market_state_hash = compute_market_state_hash(market_state)
        record = DecisionRecordV1(
            schema_version="dr.v1",
            run_id=self._run_id,
            seq=self._seq,
            ts_utc=_utc_timestamp(),
            timeframe=timeframe,
            risk_state=risk_state,
            market_state=market_state,
            market_state_hash=market_state_hash,
            selection=selection,
        )
        self._file.write(record.to_json_line())
        self._file.flush()
        os.fsync(self._file.fileno())
        self._seq += 1
        return record

    def close(self) -> None:
        self._file.close()
