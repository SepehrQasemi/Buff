"""Artifacts writer for fundamental risk decisions."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .engine import FundamentalRiskDecision


def _decision_to_dict(decision: FundamentalRiskDecision) -> dict[str, Any]:
    data = asdict(decision)
    data["timestamp"] = decision.timestamp.isoformat()
    data["evidence"] = [
        {
            "rule_id": item.rule_id,
            "domain": item.domain,
            "matched": item.matched,
            "severity": item.severity,
            "reason": item.reason,
        }
        for item in decision.evidence
    ]
    return data


def write_latest(decision: FundamentalRiskDecision, path: str | Path) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _decision_to_dict(decision)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_timeline(decision: FundamentalRiskDecision, path: str | Path) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    history: list[dict[str, Any]] = []
    if out_path.exists():
        history = json.loads(out_path.read_text(encoding="utf-8"))
        if not isinstance(history, list):
            raise ValueError("timeline_not_list")
    history.append(_decision_to_dict(decision))
    history_sorted = sorted(history, key=lambda entry: entry.get("timestamp", ""))
    out_path.write_text(json.dumps(history_sorted, indent=2, sort_keys=True), encoding="utf-8")
