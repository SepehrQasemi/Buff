from __future__ import annotations

from typing import Any

from fastapi import HTTPException

STAGE_TOKEN = "S5_EXECUTION_SAFETY_BOUNDARIES"

_ARTIFACT_BY_CODE = {
    "decision_records_missing": "decision_records.jsonl",
    "decision_records_invalid": "decision_records.jsonl",
    "metrics_missing": "metrics.json",
    "metrics_invalid": "metrics.json",
    "ohlcv_missing": "ohlcv artifact",
    "ohlcv_invalid": "ohlcv artifact",
    "timeline_missing": "timeline artifact",
    "timeline_invalid": "timeline artifact",
    "trades_missing": "trades artifact",
    "trades_invalid": "trades artifact",
    "ARTIFACT_NOT_FOUND": "artifact",
}

_RECOVERY_HINTS = {
    "RUNS_ROOT_UNSET": "Set RUNS_ROOT to a writable local path and restart the API.",
    "RUNS_ROOT_MISSING": "Create RUNS_ROOT (or point to an existing folder) and restart the API.",
    "RUNS_ROOT_INVALID": "Point RUNS_ROOT to a directory path and restart the API.",
    "RUNS_ROOT_NOT_WRITABLE": "Fix RUNS_ROOT permissions, then retry.",
    "RUN_NOT_FOUND": "Verify the run_id and ensure it exists under RUNS_ROOT.",
    "RUN_CORRUPTED": "Recreate the run to regenerate missing artifacts.",
    "RUN_CONFIG_INVALID": "Fix the run request payload and retry.",
    "EXPERIMENT_CANDIDATES_LIMIT_EXCEEDED": "Reduce candidates to the allowed maximum and retry.",
    "EXPERIMENT_LOCK_TIMEOUT": "Retry after the experiment lock is released.",
    "RUN_ID_INVALID": "Use a valid run id with letters, numbers, underscores, or hyphens.",
    "REGISTRY_LOCK_TIMEOUT": "Retry after the registry lock is released.",
    "REGISTRY_WRITE_FAILED": "Inspect registry/index.json and retry.",
    "DATA_INVALID": "Fix CSV schema/timestamps and rerun.",
}


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_provenance(details: dict[str, Any]) -> dict[str, Any]:
    strategy_id = details.get("strategy_id")
    strategy_version = details.get("strategy_version")
    strategy_hash = details.get("strategy_hash")
    risk_level = details.get("risk_level")
    stage_token = details.get("stage_token") or STAGE_TOKEN
    return {
        "run_id": details.get("run_id"),
        "strategy": {
            "id": strategy_id if isinstance(strategy_id, str) else None,
            "version": strategy_version if isinstance(strategy_version, str) else None,
            "hash": strategy_hash if isinstance(strategy_hash, str) else None,
        },
        "risk_level": risk_level if isinstance(risk_level, int) else None,
        "stage_token": stage_token if isinstance(stage_token, str) else STAGE_TOKEN,
    }


def build_error_envelope(
    code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    normalized = _as_dict(details)
    artifact_reference = normalized.get("artifact_reference")
    if not isinstance(artifact_reference, str) or not artifact_reference.strip():
        artifact_reference = normalized.get("name")
    if not isinstance(artifact_reference, str) or not artifact_reference.strip():
        artifact_reference = _ARTIFACT_BY_CODE.get(code)

    recovery_hint = _RECOVERY_HINTS.get(code)
    if not recovery_hint:
        if code in _ARTIFACT_BY_CODE:
            recovery_hint = "Restore or regenerate the referenced artifact, then retry."
        else:
            recovery_hint = "Check API logs and artifacts, then retry."

    human_message = normalized.get("human_message")
    if not isinstance(human_message, str) or not human_message.strip():
        human_message = message

    return {
        "error_code": code,
        "human_message": human_message,
        "recovery_hint": recovery_hint,
        "artifact_reference": artifact_reference if isinstance(artifact_reference, str) else None,
        "provenance": _normalize_provenance(normalized),
    }


def build_error_payload(
    code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    normalized = _as_dict(details)
    envelope = build_error_envelope(code, message, normalized)
    payload = {
        "code": code,
        "message": message,
        "details": normalized,
        "error_envelope": envelope,
    }
    payload["error"] = {
        "code": code,
        "message": message,
        "details": normalized,
        "envelope": envelope,
    }
    return payload


def raise_api_error(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail=build_error_payload(code, message, details),
    )
