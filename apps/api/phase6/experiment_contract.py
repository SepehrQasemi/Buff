from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

EXPERIMENT_SCHEMA_VERSION = "1.0.0"

EXPERIMENT_REQUEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["schema_version", "candidates"],
    "properties": {
        "schema_version": {"type": "string", "const": EXPERIMENT_SCHEMA_VERSION},
        "name": {"type": "string"},
        "notes": {"type": "string"},
        "candidates": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["run_config"],
                "properties": {
                    "candidate_id": {"type": "string"},
                    "label": {"type": "string"},
                    "run_config": {"type": "object"},
                },
                "additionalProperties": True,
            },
        },
    },
    "additionalProperties": True,
}

_CANDIDATE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")


@dataclass
class ExperimentContractError(Exception):
    code: str
    message: str
    status_code: int
    details: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details or {},
        }


def normalize_experiment_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ExperimentContractError(
            "EXPERIMENT_CONFIG_INVALID",
            "Request body must be an object",
            400,
        )

    schema_version = str(payload.get("schema_version") or "").strip()
    if not schema_version:
        raise ExperimentContractError(
            "EXPERIMENT_CONFIG_INVALID",
            "schema_version is required",
            400,
        )
    if schema_version != EXPERIMENT_SCHEMA_VERSION:
        raise ExperimentContractError(
            "EXPERIMENT_CONFIG_INVALID",
            "schema_version is invalid",
            400,
            {"schema_version": schema_version},
        )

    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) == 0:
        raise ExperimentContractError(
            "EXPERIMENT_CONFIG_INVALID",
            "candidates must be a non-empty array",
            400,
        )

    normalized_candidates: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(raw_candidates):
        candidate = _normalize_candidate(raw_candidate, index)
        normalized_candidates.append(candidate)

    normalized: dict[str, Any] = {
        "schema_version": schema_version,
        "candidates": normalized_candidates,
    }
    for key in ("name", "notes"):
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            normalized[key] = text
    return normalized


def _normalize_candidate(raw_candidate: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw_candidate, dict):
        raise ExperimentContractError(
            "EXPERIMENT_CONFIG_INVALID",
            "candidate must be an object",
            400,
            {"candidate_index": index},
        )

    candidate_id = _normalize_candidate_id(raw_candidate.get("candidate_id"), index)
    run_config = _extract_run_config(raw_candidate, index)

    normalized: dict[str, Any] = {
        "candidate_id": candidate_id,
        "run_config": copy.deepcopy(run_config),
    }
    label = raw_candidate.get("label")
    if label is not None:
        text = str(label).strip()
        if text:
            normalized["label"] = text
    return normalized


def _normalize_candidate_id(raw_candidate_id: Any, index: int) -> str:
    if raw_candidate_id is None:
        return f"cand_{index + 1:03d}"
    candidate_id = str(raw_candidate_id).strip().lower()
    if not _CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        raise ExperimentContractError(
            "EXPERIMENT_CONFIG_INVALID",
            "candidate_id is invalid",
            400,
            {"candidate_index": index, "candidate_id": raw_candidate_id},
        )
    return candidate_id


def _extract_run_config(raw_candidate: dict[str, Any], index: int) -> dict[str, Any]:
    if "run_config" in raw_candidate:
        run_config = raw_candidate.get("run_config")
    else:
        run_config = raw_candidate
    if not isinstance(run_config, dict):
        raise ExperimentContractError(
            "EXPERIMENT_CONFIG_INVALID",
            "candidate.run_config must be an object",
            400,
            {"candidate_index": index},
        )
    return run_config
