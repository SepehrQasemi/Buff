from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .canonical import NUMERIC_POLICY_ID, canonicalize_timestamp_utc


ERROR_SCHEMA_VERSION = "s2/error/v1"
RUN_FAILURE_SCHEMA_VERSION = "s2/run_failure/v1"
FATAL_SEVERITY = "FATAL"
DEFAULT_FAILURE_TS_UTC = "1970-01-01T00:00:00Z"

ALLOWED_ERROR_CODES = frozenset(
    {
        "ARTIFACT_MISSING",
        "DATA_INTEGRITY_FAILURE",
        "DIGEST_MISMATCH",
        "INPUT_DIGEST_MISMATCH",
        "INPUT_INVALID",
        "INPUT_MISSING",
        "MISSING_CRITICAL_FUNDING_WINDOW",
        "ORDERING_INVALID",
        "SCHEMA_INVALID",
        "SIMULATION_FAILED",
    }
)

ERROR_PRECEDENCE = (
    "SCHEMA_INVALID",
    "ARTIFACT_MISSING",
    "DIGEST_MISMATCH",
    "INPUT_DIGEST_MISMATCH",
    "INPUT_MISSING",
    "INPUT_INVALID",
    "MISSING_CRITICAL_FUNDING_WINDOW",
    "DATA_INTEGRITY_FAILURE",
    "ORDERING_INVALID",
    "SIMULATION_FAILED",
)
_ERROR_PRECEDENCE_RANK = {code: idx for idx, code in enumerate(ERROR_PRECEDENCE)}


def resolve_error_code(candidates: Sequence[str]) -> str:
    valid_codes: list[str] = []
    for candidate in candidates:
        code = str(candidate).strip().upper()
        if code in ALLOWED_ERROR_CODES:
            valid_codes.append(code)
    if not valid_codes:
        return "SIMULATION_FAILED"
    return min(
        valid_codes, key=lambda code: _ERROR_PRECEDENCE_RANK.get(code, len(ERROR_PRECEDENCE))
    )


@dataclass(frozen=True)
class S2StructuredFailure:
    error_code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)
    source_component: str = "s2.artifacts"
    source_stage: str = "s2"
    source_function: str = "run_s2_artifact_pack"
    severity: str = FATAL_SEVERITY
    timestamp: str = DEFAULT_FAILURE_TS_UTC
    schema_version: str = ERROR_SCHEMA_VERSION
    numeric_policy_id: str = NUMERIC_POLICY_ID

    def to_error_payload(self) -> dict[str, Any]:
        code = str(self.error_code).strip().upper()
        if code not in ALLOWED_ERROR_CODES:
            raise ValueError(f"unsupported_error_code:{code}")
        ts_utc = canonicalize_timestamp_utc(self.timestamp)
        if self.severity != FATAL_SEVERITY:
            raise ValueError("unsupported_severity")
        return {
            "schema_version": self.schema_version,
            "numeric_policy_id": self.numeric_policy_id,
            "error_code": code,
            "severity": self.severity,
            "message": str(self.message),
            "context": dict(self.context),
            "source": {
                "component": str(self.source_component),
                "stage": str(self.source_stage),
                "function": str(self.source_function),
            },
            "timestamp": ts_utc,
        }


def deterministic_failure_timestamp(
    candidates: Sequence[str] | None, *, fallback: str = DEFAULT_FAILURE_TS_UTC
) -> str:
    normalized: list[str] = []
    for candidate in candidates or []:
        text = str(candidate).strip()
        if not text:
            continue
        normalized.append(canonicalize_timestamp_utc(text))
    if normalized:
        return sorted(normalized)[0]
    return canonicalize_timestamp_utc(fallback)


def build_run_failure_payload(
    *, run_id: str, failure: S2StructuredFailure, details: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "schema_version": RUN_FAILURE_SCHEMA_VERSION,
        "numeric_policy_id": NUMERIC_POLICY_ID,
        "run_id": str(run_id),
        "error": failure.to_error_payload(),
        "details": dict(details or {}),
    }
