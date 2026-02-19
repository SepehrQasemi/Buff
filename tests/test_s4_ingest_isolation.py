from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from control_plane.state import ControlState, SystemState
from execution.engine import execute_paper_run


pytestmark = pytest.mark.unit


def test_core_runtime_import_does_not_load_ingest_modules() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import json
import sys

import control_plane.state  # noqa: F401
import execution.engine  # noqa: F401
import risk.state_machine  # noqa: F401

forbidden = sorted(
    name
    for name in sys.modules
    if name
    in {
        "data.ingest",
        "data.offline_binance_ingest",
        "buff.data.ingest",
        "buff.data.run_ingest",
    }
)
print(json.dumps(forbidden))
raise SystemExit(1 if forbidden else 0)
"""

    env = os.environ.copy()
    src_path = str((repo_root / "src").resolve())
    existing = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = src_path if not existing else f"{src_path}{os.pathsep}{existing}"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        "core runtime imports loaded ingest modules unexpectedly:\n"
        f"stdout={proc.stdout}\n"
        f"stderr={proc.stderr}"
    )


def test_runtime_artifacts_exclude_network_and_exchange_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    outcome = execute_paper_run(
        input_data={"run_id": "s4-runtime-isolation", "timeframe": "1m"},
        features={},
        risk_decision={
            "risk_state": "RED",
            "config_version": "s4",
            "reasons": [
                {
                    "rule_id": "RISK_POLICY_MISSING",
                    "severity": "ERROR",
                    "message": "risk policy configuration is missing",
                    "details": {},
                }
            ],
        },
        selected_strategy={"name": "demo", "version": "1.0.0"},
        control_state=ControlState(state=SystemState.ARMED),
    )
    assert outcome["status"] == "blocked"

    record_path = Path("workspaces") / "s4-runtime-isolation" / "decision_records.jsonl"
    record_payload = record_path.read_text(encoding="utf-8")

    forbidden_tokens = (
        "http://",
        "https://",
        "fapi.binance.com",
        "binance",
        "alpaca",
        "ibkr",
        "coinbase",
        "kraken",
    )
    serialized_outcome = json.dumps(outcome, sort_keys=True).lower()
    serialized_record = record_payload.lower()
    for token in forbidden_tokens:
        assert token not in serialized_outcome
        assert token not in serialized_record
