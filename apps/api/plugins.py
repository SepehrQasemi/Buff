from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def list_active_plugins(artifacts_root: Path) -> dict[str, list[dict[str, Any]]]:
    active, _failed = _collect_plugins(artifacts_root)
    return active


def list_failed_plugins(artifacts_root: Path) -> dict[str, list[dict[str, Any]]]:
    _active, failed = _collect_plugins(artifacts_root)
    return failed


def _collect_plugins(
    artifacts_root: Path,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    if not artifacts_root.exists():
        return _empty_payload(), _empty_payload()

    plugins_root = artifacts_root / "plugins"
    if not plugins_root.exists():
        return _empty_payload(), _empty_payload()

    active: dict[str, list[dict[str, Any]]] = {"indicators": [], "strategies": []}
    failed: dict[str, list[dict[str, Any]]] = {"indicators": [], "strategies": []}

    for plugin_type, bucket in (("indicator", "indicators"), ("strategy", "strategies")):
        type_root = plugins_root / plugin_type
        if not type_root.exists():
            continue
        for plugin_dir in sorted(type_root.iterdir(), key=lambda p: p.name):
            if not plugin_dir.is_dir():
                continue
            validation_path = plugin_dir / "validation.json"
            record = _load_validation(validation_path, plugin_dir.name, plugin_type)
            status = record.get("status")
            if status == "PASS":
                active[bucket].append(_active_payload(record))
            elif status == "FAIL":
                failed[bucket].append(_failed_payload(record))

    for bucket in ("indicators", "strategies"):
        active[bucket] = sorted(active[bucket], key=lambda item: item.get("id") or "")
        failed[bucket] = sorted(failed[bucket], key=lambda item: item.get("id") or "")

    return active, failed


def _load_validation(path: Path, plugin_id: str, plugin_type: str) -> dict[str, Any]:
    if not path.exists():
        return _invalid_record(
            plugin_id,
            plugin_type,
            "ARTIFACT_MISSING",
            "validation.json missing.",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _invalid_record(
            plugin_id,
            plugin_type,
            "ARTIFACT_INVALID",
            f"validation.json invalid: {exc}",
        )
    if not isinstance(payload, dict):
        return _invalid_record(
            plugin_id,
            plugin_type,
            "ARTIFACT_INVALID",
            "validation.json must be an object.",
        )

    status = payload.get("status")
    if status not in {"PASS", "FAIL"}:
        return _invalid_record(
            plugin_id,
            plugin_type,
            "ARTIFACT_STATUS_INVALID",
            "validation.json status must be PASS or FAIL.",
        )

    errors = payload.get("errors")
    if status == "FAIL":
        errors = _normalize_errors(errors)
        if not errors:
            errors = [{"rule_id": "ARTIFACT_ERRORS_MISSING", "message": "errors missing."}]
    else:
        errors = [] if errors is None else _normalize_errors(errors)

    return {
        "plugin_id": payload.get("plugin_id") or plugin_id,
        "plugin_type": payload.get("plugin_type") or plugin_type,
        "status": status,
        "errors": errors,
        "validated_at_utc": payload.get("validated_at_utc"),
        "fingerprint": payload.get("fingerprint"),
        "name": payload.get("name"),
        "version": payload.get("version"),
        "category": payload.get("category"),
    }


def _normalize_errors(errors: Any) -> list[dict[str, str]]:
    if not isinstance(errors, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in errors:
        if not isinstance(item, dict):
            continue
        rule_id = item.get("rule_id")
        message = item.get("message")
        if not rule_id or not message:
            continue
        normalized.append({"rule_id": str(rule_id), "message": str(message)})
    return normalized


def _active_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("plugin_id"),
        "name": record.get("name"),
        "version": record.get("version"),
        "category": record.get("category"),
        "validated_at_utc": record.get("validated_at_utc"),
        "fingerprint": record.get("fingerprint"),
    }


def _failed_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("plugin_id"),
        "status": record.get("status"),
        "errors": record.get("errors") or [],
        "validated_at_utc": record.get("validated_at_utc"),
        "fingerprint": record.get("fingerprint"),
    }


def _invalid_record(
    plugin_id: str,
    plugin_type: str,
    rule_id: str,
    message: str,
) -> dict[str, Any]:
    return {
        "plugin_id": plugin_id,
        "plugin_type": plugin_type,
        "status": "FAIL",
        "errors": [{"rule_id": rule_id, "message": message}],
        "validated_at_utc": None,
        "fingerprint": None,
    }


def _empty_payload() -> dict[str, list[dict[str, Any]]]:
    return {"indicators": [], "strategies": []}
