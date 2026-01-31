"""Integration tests for fundamental permission adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from risk_fundamental.integration import apply_fundamental_permission


@dataclass
class DecisionStub:
    action: str
    reason: str
    status: str = "ok"
    size_multiplier: float = 1.0
    block_reason: str | None = None
    fundamental_risk: dict | None = None


def _load_snapshots() -> list[dict]:
    path = Path("tests/fixtures/fundamental_snapshots.json")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def test_red_blocks_action() -> None:
    snapshots = _load_snapshots()
    decision = DecisionStub(action="placed", reason="ok")
    updated, _fundamental = apply_fundamental_permission(
        decision,
        snapshots[1],
        enabled=True,
    )
    assert updated.action == "blocked"
    assert updated.size_multiplier == 0.0
    assert updated.block_reason == "fundamental_risk_red"
    assert updated.fundamental_risk is not None
    assert updated.fundamental_risk["final_risk_state"] == "red"


def test_yellow_scales_size() -> None:
    snapshots = _load_snapshots()
    yellow_snapshot = {
        "timestamp": snapshots[0]["timestamp"],
        "macro": snapshots[0]["macro"],
        "onchain": {
            "nvt_ratio": 1.0,
            "mvrv_ratio": 2.0,
            "exchange_netflow_zscore": 0.0,
        },
        "news": snapshots[0]["news"],
    }
    decision = DecisionStub(action="placed", reason="ok")
    updated, _fundamental = apply_fundamental_permission(
        decision,
        yellow_snapshot,
        enabled=True,
    )
    assert updated.action == "placed"
    assert updated.size_multiplier <= 0.35
    assert updated.fundamental_risk is not None


def test_green_unchanged() -> None:
    snapshots = _load_snapshots()
    decision = DecisionStub(action="placed", reason="ok")
    updated, _fundamental = apply_fundamental_permission(
        decision,
        snapshots[0],
        enabled=True,
    )
    assert updated.action == "placed"
    assert updated.size_multiplier == 1.0
    assert updated.fundamental_risk is not None
    assert updated.fundamental_risk["final_risk_state"] == "green"


def test_missing_critical_never_green() -> None:
    snapshots = _load_snapshots()
    missing_snapshot = {
        "timestamp": snapshots[0]["timestamp"],
        "macro": snapshots[0]["macro"],
        "onchain": {},
        "news": snapshots[0]["news"],
    }
    decision = DecisionStub(action="placed", reason="ok")
    updated, _fundamental = apply_fundamental_permission(
        decision,
        missing_snapshot,
        enabled=True,
    )
    assert updated.fundamental_risk is not None
    assert updated.fundamental_risk["final_risk_state"] != "green"
