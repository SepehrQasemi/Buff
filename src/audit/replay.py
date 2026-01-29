from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from audit.decision_records import compute_market_state_hash, parse_json_line
from selector.selector import select_strategy

_LAST_LOAD_ERRORS = 0


@dataclass(frozen=True)
class ReplayResult:
    total: int
    matched: int
    mismatched: int
    hash_mismatch: int
    errors: int


def load_decision_records(path: str) -> list[dict]:
    records: list[dict] = []
    errors = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = parse_json_line(line)
            if record.get("schema_version") != "dr.v1":
                raise ValueError("schema_version")
            required = {
                "run_id",
                "seq",
                "timeframe",
                "risk_state",
                "market_state",
                "market_state_hash",
                "selection",
            }
            if not required.issubset(record.keys()):
                raise ValueError("missing_required_fields")
            records.append(record)
        except Exception:
            errors += 1
    global _LAST_LOAD_ERRORS
    _LAST_LOAD_ERRORS = errors
    return records


def normalize_selection(sel: dict) -> dict:
    return {
        "strategy_id": sel.get("strategy_id"),
        "engine_id": sel.get("engine_id"),
        "reason": sel.get("reason", []),
    }


def replay_verify(*, records_path: str) -> ReplayResult:
    records = load_decision_records(records_path)
    errors = _LAST_LOAD_ERRORS

    total = len(records)
    matched = 0
    mismatched = 0
    hash_mismatch = 0
    details: list[dict] = []

    for record in records:
        expected_hash = record.get("market_state_hash")
        computed_hash = compute_market_state_hash(record.get("market_state", {}))
        if computed_hash != expected_hash:
            hash_mismatch += 1
            continue

        out = select_strategy(
            market_state=record.get("market_state", {}),
            risk_state=record.get("risk_state", ""),
            timeframe=record.get("timeframe", ""),
            record_writer=None,
        )
        expected = normalize_selection(record.get("selection", {}))
        got = normalize_selection(out)
        if expected == got:
            matched += 1
        else:
            mismatched += 1
            if len(details) < 20:
                details.append(
                    {
                        "seq": record.get("seq"),
                        "expected": expected,
                        "got": got,
                    }
                )

    if details:
        print(json.dumps({"mismatches": details}, indent=2))

    return ReplayResult(
        total=total,
        matched=matched,
        mismatched=mismatched,
        hash_mismatch=hash_mismatch,
        errors=errors,
    )
