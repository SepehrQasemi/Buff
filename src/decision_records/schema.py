from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TypedDict


SCHEMA_VERSION = "1.0"


class ControlStatus(str, Enum):
    ARMED = "ARMED"
    DISARMED = "DISARMED"


class Environment(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class RiskStatus(str, Enum):
    GREEN = "GREEN"
    RED = "RED"


class ExecutionStatus(str, Enum):
    EXECUTED = "EXECUTED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class StrategyRef(TypedDict):
    name: str
    version: str


class ArtifactPaths(TypedDict):
    decision_records: str


class DecisionRecord(TypedDict):
    schema_version: str
    run_id: str
    timestamp_utc: str
    environment: str
    control_status: str
    strategy: StrategyRef
    risk_status: str
    execution_status: str
    reason: str | None
    inputs_digest: str
    artifact_paths: ArtifactPaths


def _is_relative_path(path_str: str) -> bool:
    path = Path(path_str)
    if path.is_absolute():
        return False
    if any(part == ".." for part in path.parts):
        return False
    return True


def _is_utc_iso8601(ts: str) -> bool:
    if not isinstance(ts, str):
        return False
    if ts.endswith("Z"):
        return True
    if ts.endswith("+00:00"):
        return True
    return False


def validate_decision_record(record: dict) -> None:
    required_keys = {
        "schema_version",
        "run_id",
        "timestamp_utc",
        "environment",
        "control_status",
        "strategy",
        "risk_status",
        "execution_status",
        "inputs_digest",
        "artifact_paths",
    }
    missing = [key for key in required_keys if key not in record]
    if missing:
        raise ValueError(f"missing_keys:{missing}")

    if record["schema_version"] != SCHEMA_VERSION:
        raise ValueError("invalid_schema_version")

    if not isinstance(record["run_id"], str) or not record["run_id"]:
        raise ValueError("invalid_run_id")

    if not isinstance(record["inputs_digest"], str) or not record["inputs_digest"]:
        raise ValueError("invalid_inputs_digest")

    if not _is_utc_iso8601(record["timestamp_utc"]):
        raise ValueError("invalid_timestamp_utc")

    if record["environment"] not in {e.value for e in Environment}:
        raise ValueError("invalid_environment")
    if record["control_status"] not in {e.value for e in ControlStatus}:
        raise ValueError("invalid_control_status")
    if record["risk_status"] not in {e.value for e in RiskStatus}:
        raise ValueError("invalid_risk_status")
    if record["execution_status"] not in {e.value for e in ExecutionStatus}:
        raise ValueError("invalid_execution_status")

    strategy = record["strategy"]
    if not isinstance(strategy, dict):
        raise ValueError("invalid_strategy")
    if not isinstance(strategy.get("name"), str) or not strategy.get("name"):
        raise ValueError("invalid_strategy_name")
    if not isinstance(strategy.get("version"), str) or not strategy.get("version"):
        raise ValueError("invalid_strategy_version")

    if record["execution_status"] in {ExecutionStatus.BLOCKED.value, ExecutionStatus.ERROR.value}:
        reason = record.get("reason")
        if not isinstance(reason, str) or not reason:
            raise ValueError("missing_reason")

    artifact_paths = record["artifact_paths"]
    if not isinstance(artifact_paths, dict):
        raise ValueError("invalid_artifact_paths")
    decision_path = artifact_paths.get("decision_records")
    if not isinstance(decision_path, str) or not decision_path:
        raise ValueError("invalid_decision_records_path")
    if not _is_relative_path(decision_path):
        raise ValueError("decision_records_path_not_relative")
