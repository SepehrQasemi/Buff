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


def _is_utc_iso8601(ts: object) -> bool:
    if not isinstance(ts, str):
        return False
    return ts.endswith("Z") or ts.endswith("+00:00")


def validate_decision_record_v1(record: dict) -> None:
    if record.get("schema_version") != "dr.v1":
        raise ValueError("invalid_schema_version")
    if not isinstance(record.get("run_id"), str) or not record.get("run_id"):
        raise ValueError("invalid_run_id")
    if not isinstance(record.get("seq"), int):
        raise ValueError("invalid_seq")
    if not _is_utc_iso8601(record.get("ts_utc")):
        raise ValueError("invalid_ts_utc")
    if not isinstance(record.get("timeframe"), str) or not record.get("timeframe"):
        raise ValueError("invalid_timeframe")
    if not isinstance(record.get("risk_state"), str) or not record.get("risk_state"):
        raise ValueError("invalid_risk_state")
    if not isinstance(record.get("market_state"), dict):
        raise ValueError("invalid_market_state")
    if not isinstance(record.get("market_state_hash"), str) or not record.get("market_state_hash"):
        raise ValueError("invalid_market_state_hash")
    if not isinstance(record.get("selection"), dict):
        raise ValueError("invalid_selection")


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


def make_records_path(run_id: str, *, shard_index: int) -> str:
    path = Path("runs") / run_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path / f"decision_records_{shard_index:04d}.jsonl")


def infer_next_seq_from_jsonl(path: str) -> int:
    jsonl_path = Path(path)
    if not jsonl_path.exists():
        return 0
    last_seq: int | None = None
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = parse_json_line(line)
            seq = record.get("seq")
            if isinstance(seq, int):
                last_seq = seq
        except Exception:
            continue
    if last_seq is None:
        return 0
    return last_seq + 1


def infer_next_shard_and_seq(run_dir: str) -> tuple[int, int]:
    run_path = Path(run_dir)
    if not run_path.exists():
        return 0, 0
    shard_indices: list[int] = []
    for path in run_path.glob("decision_records_*.jsonl"):
        try:
            shard_indices.append(int(path.stem.split("_")[-1]))
        except ValueError:
            continue
    if not shard_indices:
        return 0, 0
    shard_index = max(shard_indices)
    records_path = run_path / f"decision_records_{shard_index:04d}.jsonl"
    next_seq = infer_next_seq_from_jsonl(str(records_path))
    return shard_index, next_seq


def _utc_timestamp() -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    if ts.endswith("+00:00"):
        return ts.replace("+00:00", "Z")
    return ts


class DecisionRecordWriter:
    def __init__(self, *, out_path: str, run_id: str, start_seq: int = 0) -> None:
        self._file = open(out_path, "a", encoding="utf-8")
        self._ensure_newline(out_path)
        self._run_id = run_id
        self._seq = start_seq

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
        validate_decision_record_v1(asdict(record))
        self._file.write(record.to_json_line())
        self._file.flush()
        os.fsync(self._file.fileno())
        self._seq += 1
        return record

    def close(self) -> None:
        self._file.close()

    def _ensure_newline(self, path: str) -> None:
        file_path = Path(path)
        if not file_path.exists():
            return
        if file_path.stat().st_size == 0:
            return
        with file_path.open("rb") as handle:
            handle.seek(-1, os.SEEK_END)
            last_byte = handle.read(1)
        if last_byte != b"\n":
            self._file.write("\n")
            self._file.flush()
