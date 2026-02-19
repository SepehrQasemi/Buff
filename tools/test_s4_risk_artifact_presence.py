from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from control_plane.state import ControlState, SystemState
from execution.engine import execute_paper_run
from risk.contracts import verify_risk_decision_hash

SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_RISK_KEYS = {"decision", "reasons", "config_version", "inputs_digest", "stable_hash"}
OPTIONAL_RISK_KEYS = {"permission", "reason_details", "pack_id", "pack_version"}


def _is_json_tree(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_tree(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_tree(item) for key, item in value.items())
    return False


def _assert_structured_reason(reason: object) -> None:
    assert isinstance(reason, dict), "risk reasons must be structured dicts"
    assert set(reason.keys()) == {"rule_id", "severity", "message", "details"}, (
        f"risk reason keys must be stable; found: {sorted(reason.keys())}"
    )
    rule_id = reason.get("rule_id")
    severity = reason.get("severity")
    message = reason.get("message")
    details = reason.get("details")

    assert isinstance(rule_id, str) and rule_id.strip(), "rule_id must be non-empty"
    assert isinstance(severity, str) and severity.strip(), "severity must be non-empty"
    assert isinstance(message, str) and message.strip(), "message must be non-empty"
    assert isinstance(details, dict), "details must be a dict"
    assert _is_json_tree(details), "details must be JSON-serializable primitives"


def _is_deny_decision(decision: str, permission: str | None) -> bool:
    decision_normalized = decision.strip().upper()
    permission_normalized = permission.strip().upper() if isinstance(permission, str) else ""
    return decision_normalized in {
        "DENY",
        "REJECT",
        "RED",
        "BLOCK",
        "BLOCKED",
    } or permission_normalized in {"DENY", "REJECT", "BLOCK", "BLOCKED"}


def test_s4_risk_artifact_presence_on_runtime_artifact(tmp_path: Path) -> None:
    run_id = "s4-risk-v2-artifact"
    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        outcome = execute_paper_run(
            input_data={"run_id": run_id, "timeframe": "1m"},
            features={},
            risk_decision={
                "risk_state": "RED",
                "config_version": "risk-v2",
                "reasons": [
                    {
                        "rule_id": "RISK_POLICY_MISSING",
                        "severity": "ERROR",
                        "message": "risk policy configuration is missing",
                        "details": {"source": "gate"},
                    }
                ],
            },
            selected_strategy={"name": "s4-demo", "version": "1.0.0"},
            control_state=ControlState(state=SystemState.ARMED),
        )
        assert outcome.get("status") == "blocked"

        records_path = Path("workspaces") / run_id / "decision_records.jsonl"
        assert records_path.exists(), "decision_records artifact missing"
        lines = [line for line in records_path.read_text(encoding="utf-8").splitlines() if line]
        assert lines, "decision_records artifact is empty"
        record = json.loads(lines[-1])

        risk_block = record.get("risk")
        assert isinstance(risk_block, dict), "risk block missing from decision artifact"
        assert REQUIRED_RISK_KEYS.issubset(set(risk_block.keys())), (
            f"missing risk keys: {sorted(REQUIRED_RISK_KEYS - set(risk_block.keys()))}"
        )
        unexpected = set(risk_block.keys()) - (REQUIRED_RISK_KEYS | OPTIONAL_RISK_KEYS)
        assert not unexpected, f"unexpected risk keys: {sorted(unexpected)}"

        decision = risk_block.get("decision")
        permission = risk_block.get("permission")
        assert isinstance(decision, str) and decision.strip(), "risk.decision must be non-empty"
        if permission is not None:
            assert isinstance(permission, str) and permission.strip(), (
                "risk.permission must be non-empty when present"
            )

        config_version = risk_block.get("config_version")
        assert isinstance(config_version, str) and config_version.strip(), (
            "risk.config_version must be a non-empty string"
        )

        inputs_digest = risk_block.get("inputs_digest")
        assert isinstance(inputs_digest, str) and SHA256_HEX_RE.fullmatch(inputs_digest), (
            "risk.inputs_digest must be a 64-char sha256 hex"
        )
        stable_hash = risk_block.get("stable_hash")
        assert isinstance(stable_hash, str) and SHA256_HEX_RE.fullmatch(stable_hash), (
            "risk.stable_hash must be a 64-char sha256 hex"
        )

        reasons = risk_block.get("reasons")
        assert isinstance(reasons, list), "risk.reasons must be a list"
        if _is_deny_decision(decision, permission if isinstance(permission, str) else None):
            assert reasons, "deny/reject decisions must include at least one reason"
        for reason in reasons:
            _assert_structured_reason(reason)

        reason_details = risk_block.get("reason_details")
        if reason_details is not None:
            assert isinstance(reason_details, list), "reason_details must be a list"
            for entry in reason_details:
                _assert_structured_reason(entry)
            json.dumps(reason_details, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

        pack_id = risk_block.get("pack_id")
        if pack_id is not None:
            assert isinstance(pack_id, str) and pack_id.strip(), "risk.pack_id must be non-empty"
        pack_version = risk_block.get("pack_version")
        if pack_version is not None:
            assert isinstance(pack_version, str) and pack_version.strip(), (
                "risk.pack_version must be non-empty"
            )

        assert verify_risk_decision_hash(
            decision=decision,
            reasons=reasons,
            config_version=config_version,
            inputs_digest=inputs_digest,
            stable_hash=stable_hash,
            pack_id=pack_id if isinstance(pack_id, str) else None,
            pack_version=pack_version if isinstance(pack_version, str) else None,
        ), "risk.stable_hash must match recomputed canonical hash"
    finally:
        os.chdir(cwd)
