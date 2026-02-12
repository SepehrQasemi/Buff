from __future__ import annotations

ALLOWED_REASON_CODE_PREFIXES = (
    "MISSING_FILE:",
    "INVALID_TYPE:",
    "INVALID_ENUM:",
    "SCHEMA_MISSING_FIELD:",
    "SCHEMA_UNKNOWN_FIELD:",
    "INTERFACE_MISSING:",
    "FORBIDDEN_IMPORT:",
    "FORBIDDEN_CALL:",
    "FORBIDDEN_ATTRIBUTE:",
    "NON_DETERMINISTIC_API:",
)

ALLOWED_REASON_CODES = {
    "YAML_PARSE_ERROR",
    "AST_PARSE_ERROR",
    "AST_UNCERTAIN",
    "VALIDATION_EXCEPTION",
    "GLOBAL_STATE_RISK",
    "SOURCE_HASH_ERROR",
    "ARTIFACT_WRITE_ERROR",
    "ARTIFACT_INVALID",
    "ARTIFACT_MISSING",
    "TOO_LARGE",
}


def is_allowed_reason_code(code: str) -> bool:
    if code in ALLOWED_REASON_CODES:
        return True
    return any(code.startswith(prefix) for prefix in ALLOWED_REASON_CODE_PREFIXES)
