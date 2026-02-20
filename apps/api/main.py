from __future__ import annotations

import hashlib
import io
import json
import os
import re
import uuid
import zipfile
from email.parser import BytesParser
from email.policy import default as email_default
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .artifacts import (
    build_summary,
    build_timeline_from_decisions,
    collect_error_records,
    collect_run_artifacts,
    discover_runs,
    filter_decisions,
    find_timeline_path,
    get_artifacts_root,
    load_metrics,
    load_ohlcv,
    load_ohlcv_jsonl,
    load_timeline,
    load_trade_markers,
    load_trade_markers_jsonl,
    load_trades,
    load_trades_jsonl,
    resolve_ohlcv_path,
    resolve_ohlcv_jsonl_path,
    resolve_run_dir,
    stream_decisions_export,
    stream_errors_export,
    stream_trades_export,
    validate_decision_records,
)
from .chat import router as chat_router
from .errors import build_error_envelope, build_error_payload, raise_api_error
from .plugins import get_validation_summary, list_active_plugins, list_failed_plugins
from .phase6.canonical import write_canonical_json
from .phase6.http import error_response
from .phase6.paths import (
    RUNS_ROOT_ENV,
    get_runs_root,
    is_valid_component,
    is_within_root,
    user_imports_root,
    user_root,
    user_runs_root,
    user_uploads_root,
)
from .phase6.registry import (
    build_registry_entry,
    has_legacy_runs,
    list_legacy_run_dirs,
    lock_registry,
    migrate_legacy_runs,
    reconcile_registry,
)
from .phase6.run_builder import (
    RunBuilderError,
    create_run,
    inspect_csv_path,
    list_builtin_strategies,
    normalize_strategy_request,
)
from .security.user_context import UserContext, UserContextError, resolve_user_context
from .timeutils import coerce_ts_param

router = APIRouter()
KILL_SWITCH_ENV = "BUFF_KILL_SWITCH"
DEMO_MODE_ENV = "DEMO_MODE"
DEFAULT_USER_ENV = "BUFF_DEFAULT_USER"
API_VERSION = "1"
STAGE_TOKEN = "S5_EXECUTION_SAFETY_BOUNDARIES"
DATASET_MAX_BYTES = 10 * 1024 * 1024
DATASET_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
DATASET_DEFAULT_SYMBOL = "LOCAL"
DATASET_DEFAULT_TIMEFRAME = "1m"


def _kill_switch_enabled() -> bool:
    return os.getenv(KILL_SWITCH_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _demo_mode_enabled() -> bool:
    return os.getenv(DEMO_MODE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _utc_now_iso() -> str:
    text = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text


def _canonical_hash(value: object) -> str | None:
    if value is None:
        return None
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except TypeError:
        return None
    return hashlib.sha256(encoded).hexdigest()


def _resolve_stage_token(manifest: dict[str, object]) -> str:
    meta = manifest.get("meta")
    if isinstance(meta, dict):
        token = meta.get("stage_token")
        if isinstance(token, str):
            token = token.strip()
            if token:
                return token
    return STAGE_TOKEN


def _read_registry_payload_read_only(user_root_path: Path) -> tuple[dict[str, object], str | None]:
    registry_path = user_root_path / "index.json"
    if not registry_path.exists():
        return {"schema_version": "1.0.0", "generated_at": None, "runs": []}, None
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"schema_version": "1.0.0", "generated_at": None, "runs": []}, str(exc)
    if not isinstance(payload, dict):
        return {"schema_version": "1.0.0", "generated_at": None, "runs": []}, "index.json invalid"
    runs = payload.get("runs")
    if not isinstance(runs, list):
        return {
            "schema_version": "1.0.0",
            "generated_at": None,
            "runs": [],
        }, "index.json runs invalid"
    return payload, None


def _iter_candidate_run_dirs(runs_root: Path) -> Iterable[Path]:
    if not runs_root.exists() or not runs_root.is_dir():
        return []
    candidates: list[Path] = []
    for child in sorted(runs_root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        name = child.name.strip()
        if not name or name.startswith("."):
            continue
        lowered = name.lower()
        if lowered in {"inputs", "__pycache__", "tmp", "temp", "users"}:
            continue
        if lowered.startswith("tmp_") or lowered.startswith("tmp-"):
            continue
        if lowered.startswith(".tmp_") or lowered.startswith(".tmp-"):
            continue
        has_sentinel = (child / "manifest.json").exists() or (
            child / "decision_records.jsonl"
        ).exists()
        if not has_sentinel:
            continue
        candidates.append(child.resolve())
    return candidates


def _build_missing_registry_entry(
    run_id: str, existing: dict[str, object], *, user_id: str
) -> dict[str, object]:
    created_at = existing.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        created_at = _utc_now_iso()
    return {
        "run_id": run_id,
        "created_at": created_at,
        "owner_user_id": user_id,
        "status": "CORRUPTED",
        "health": "CORRUPTED",
        "artifacts_present": [],
        "missing_artifacts": ["run_dir"],
        "invalid_artifacts": [],
        "checks": {"required": {"run_dir": {"status": "missing"}}, "json_parse": {}},
        "last_verified_at": _utc_now_iso(),
        "meta": {
            "owner_user_id": user_id,
            "observed_read_only": True,
        },
    }


def _collect_registry_entries_read_only(
    owner_root: Path,
    runs_root: Path,
    *,
    user_id: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    payload, registry_error = _read_registry_payload_read_only(owner_root)
    raw_runs = payload.get("runs")
    runs_from_index = raw_runs if isinstance(raw_runs, list) else []

    index_map: dict[str, dict[str, object]] = {}
    invalid_entries = 0
    for raw in runs_from_index:
        if not isinstance(raw, dict):
            invalid_entries += 1
            continue
        run_id = str(raw.get("run_id") or "").strip()
        if not run_id:
            invalid_entries += 1
            continue
        if run_id in index_map:
            invalid_entries += 1
            continue
        index_map[run_id] = raw

    entries: list[dict[str, object]] = []
    seen: set[str] = set()
    for run_id in sorted(index_map):
        raw = index_map[run_id]
        seen.add(run_id)
        run_dir = (runs_root / run_id).resolve()
        if not is_within_root(run_dir, runs_root) or not run_dir.exists() or not run_dir.is_dir():
            entries.append(_build_missing_registry_entry(run_id, raw, user_id=user_id))
            continue
        manifest = _load_manifest(run_dir)
        status_hint = raw.get("status")
        fallback_status = str(status_hint) if isinstance(status_hint, str) else None
        entries.append(
            build_registry_entry(
                run_dir,
                manifest,
                user_id=user_id,
                fallback_status=fallback_status,
            )
        )

    for run_dir in _iter_candidate_run_dirs(runs_root):
        run_id = run_dir.name
        if run_id in seen:
            continue
        manifest = _load_manifest(run_dir)
        entries.append(build_registry_entry(run_dir, manifest, user_id=user_id))

    entries = sorted(entries, key=lambda item: str(item.get("run_id") or ""))
    metadata = {
        "registry_error": registry_error,
        "invalid_entries": invalid_entries,
        "index_path": str((owner_root / "index.json").resolve()),
    }
    return entries, metadata


def _artifact_status(entry: dict[str, object]) -> str:
    missing = _normalize_artifact_list(entry.get("missing_artifacts"))
    invalid = _normalize_artifact_list(entry.get("invalid_artifacts"))
    if missing:
        return "missing"
    if invalid:
        return "corrupt"
    return "present"


def _validation_status(entry: dict[str, object]) -> str:
    return "pass" if _artifact_status(entry) == "present" else "fail"


def _error_code_for_entry(entry: dict[str, object]) -> str | None:
    status = _artifact_status(entry)
    if status == "missing":
        return "RUN_CORRUPTED"
    if status == "corrupt":
        return "RUN_ARTIFACT_INVALID"
    return None


def _manifest_provenance(
    run_id: str, manifest: dict[str, object], entry: dict[str, object]
) -> dict[str, object]:
    strategy = manifest.get("strategy")
    strategy_obj = strategy if isinstance(strategy, dict) else {}
    risk = manifest.get("risk")
    risk_obj = risk if isinstance(risk, dict) else {}
    strategy_id_raw = strategy_obj.get("id") or entry.get("strategy_id")
    strategy_id = str(strategy_id_raw) if strategy_id_raw is not None else None
    strategy_version_raw = strategy_obj.get("version")
    strategy_version = str(strategy_version_raw) if strategy_version_raw is not None else None
    strategy_hash = _canonical_hash(strategy_obj if strategy_obj else strategy_id)
    risk_level = risk_obj.get("level")
    if not isinstance(risk_level, int):
        risk_level = None
    return {
        "run_id": run_id,
        "strategy": {
            "id": strategy_id,
            "version": strategy_version,
            "hash": strategy_hash,
        },
        "risk_level": risk_level,
        "risk_config_hash": _canonical_hash(risk_obj if risk_obj else None),
        "stage_token": _resolve_stage_token(manifest),
        "created_at": manifest.get("created_at"),
    }


def _error_envelope_for_entry(
    run_id: str, entry: dict[str, object], manifest: dict[str, object]
) -> dict[str, object] | None:
    code = _error_code_for_entry(entry)
    if code is None:
        return None
    provenance = _manifest_provenance(run_id, manifest, entry)
    strategy = provenance.get("strategy")
    strategy_obj = strategy if isinstance(strategy, dict) else {}
    details: dict[str, object] = {
        "run_id": run_id,
        "strategy_id": strategy_obj.get("id"),
        "strategy_version": strategy_obj.get("version"),
        "strategy_hash": strategy_obj.get("hash"),
        "risk_level": provenance.get("risk_level"),
        "stage_token": provenance.get("stage_token"),
        "artifact_reference": ",".join(
            _normalize_artifact_list(entry.get("missing_artifacts"))
            or _normalize_artifact_list(entry.get("invalid_artifacts"))
        )
        or None,
    }
    if code == "RUN_CORRUPTED":
        message = "Run artifacts missing"
    else:
        message = "Run artifacts invalid"
    return build_error_envelope(code, message, details)


def _artifact_digests(run_dir: Path) -> list[dict[str, object]]:
    if not run_dir.exists() or not run_dir.is_dir():
        return []
    files: list[dict[str, object]] = []
    for child in sorted(run_dir.iterdir(), key=lambda item: item.name):
        if not child.is_file():
            continue
        digest = hashlib.sha256()
        with child.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        files.append(
            {
                "name": child.name,
                "sha256": digest.hexdigest(),
                "size_bytes": child.stat().st_size,
            }
        )
    return files


def _check_runs_root_writable(runs_root: Path) -> tuple[bool, str | None]:
    probe = runs_root / f".buff_write_check_{os.getpid()}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return False, str(exc)
    return True, None


def _runs_root_readiness() -> tuple[Path, dict[str, object]] | JSONResponse:
    runs_root = get_runs_root()
    if runs_root is None:
        return error_response(
            503,
            "RUNS_ROOT_UNSET",
            "RUNS_ROOT is not set",
            {"env": RUNS_ROOT_ENV},
        )
    if not runs_root.exists():
        return error_response(
            503,
            "RUNS_ROOT_MISSING",
            "RUNS_ROOT does not exist",
            {"path": str(runs_root)},
        )
    if not runs_root.is_dir():
        return error_response(
            503,
            "RUNS_ROOT_INVALID",
            "RUNS_ROOT is not a directory",
            {"path": str(runs_root)},
        )
    writable, error = _check_runs_root_writable(runs_root)
    if not writable:
        return error_response(
            503,
            "RUNS_ROOT_NOT_WRITABLE",
            "RUNS_ROOT is not writable",
            {"path": str(runs_root), "error": error or "permission denied"},
        )
    return runs_root, {"status": "ok", "path": str(runs_root), "writable": True}


def _runs_root_readiness_check() -> tuple[dict[str, object], Path | None]:
    runs_root = get_runs_root()
    if runs_root is None:
        return (
            {
                "name": "runs_root",
                "ok": False,
                "code": "RUNS_ROOT_UNSET",
                "message": "RUNS_ROOT is not set",
                "details": {"env": RUNS_ROOT_ENV},
            },
            None,
        )
    if not runs_root.exists():
        return (
            {
                "name": "runs_root",
                "ok": False,
                "code": "RUNS_ROOT_MISSING",
                "message": "RUNS_ROOT does not exist",
                "details": {"path": str(runs_root)},
            },
            None,
        )
    if not runs_root.is_dir():
        return (
            {
                "name": "runs_root",
                "ok": False,
                "code": "RUNS_ROOT_INVALID",
                "message": "RUNS_ROOT is not a directory",
                "details": {"path": str(runs_root)},
            },
            None,
        )
    writable, error = _check_runs_root_writable(runs_root)
    if not writable:
        return (
            {
                "name": "runs_root",
                "ok": False,
                "code": "RUNS_ROOT_NOT_WRITABLE",
                "message": "RUNS_ROOT is not writable",
                "details": {"path": str(runs_root), "error": error or "permission denied"},
            },
            None,
        )
    return (
        {
            "name": "runs_root",
            "ok": True,
            "code": "OK",
            "message": "RUNS_ROOT ready",
            "details": {"path": str(runs_root), "writable": True},
        },
        runs_root,
    )


def _readiness_registry_and_integrity_checks(base_runs_root: Path) -> list[dict[str, object]]:
    users_root = base_runs_root / "users"
    if not users_root.exists() or not users_root.is_dir():
        return [
            {
                "name": "registry_access",
                "ok": True,
                "code": "OK",
                "message": "No user registries found",
                "details": {"users_checked": 0},
            },
            {
                "name": "run_integrity",
                "ok": True,
                "code": "OK",
                "message": "No corrupted runs detected",
                "details": {"corrupted_runs": []},
            },
        ]

    users_checked = 0
    registry_errors: list[dict[str, object]] = []
    corrupted_runs: list[str] = []

    for user_dir in sorted(users_root.iterdir(), key=lambda item: item.name):
        if not user_dir.is_dir():
            continue
        user_id = user_dir.name
        users_checked += 1
        runs_root = user_runs_root(base_runs_root, user_id)
        entries, metadata = _collect_registry_entries_read_only(
            user_dir, runs_root, user_id=user_id
        )
        registry_error = metadata.get("registry_error")
        if isinstance(registry_error, str) and registry_error:
            registry_errors.append(
                {
                    "user_id": user_id,
                    "index_path": metadata.get("index_path"),
                    "error": registry_error,
                }
            )
        for entry in entries:
            run_id = str(entry.get("run_id") or "").strip()
            if not run_id:
                continue
            status = str(entry.get("status") or "").upper()
            health = str(entry.get("health") or "").upper()
            if status == "CORRUPTED" or health == "CORRUPTED":
                corrupted_runs.append(f"{user_id}:{run_id}")

    registry_check = {
        "name": "registry_access",
        "ok": len(registry_errors) == 0,
        "code": "OK" if len(registry_errors) == 0 else "REGISTRY_UNREADABLE",
        "message": "Registry readable"
        if len(registry_errors) == 0
        else "Registry access errors found",
        "details": {
            "users_checked": users_checked,
            "errors": registry_errors,
        },
    }
    integrity_check = {
        "name": "run_integrity",
        "ok": len(corrupted_runs) == 0,
        "code": "OK" if len(corrupted_runs) == 0 else "CORRUPTED_RUNS_DETECTED",
        "message": "No corrupted runs detected"
        if len(corrupted_runs) == 0
        else "Corrupted runs detected",
        "details": {
            "users_checked": users_checked,
            "corrupted_runs": corrupted_runs,
        },
    }
    return [registry_check, integrity_check]


def _ready_payload(checks: list[dict[str, object]]) -> dict[str, object]:
    ready = all(bool(item.get("ok")) for item in checks)
    return {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
        "timestamp": _utc_now_iso(),
        "version": API_VERSION,
        "stage_token": STAGE_TOKEN,
    }


def _resolve_user_context(request: Request) -> UserContext | JSONResponse:
    # Use `request.url.path` as the single canonical source for HMAC path input.
    # Query params are excluded by Starlette here; auth-layer normalization handles trailing slash policy.
    try:
        return resolve_user_context(request.headers, request.method, request.url.path)
    except UserContextError as exc:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)


def _resolve_user_scope(
    request: Request,
) -> tuple[UserContext, Path, Path, Path, dict[str, object]] | JSONResponse:
    user_ctx = _resolve_user_context(request)
    if isinstance(user_ctx, JSONResponse):
        return user_ctx
    readiness = _runs_root_readiness()
    if isinstance(readiness, JSONResponse):
        return readiness
    base_runs_root, runs_check = readiness
    owner_root = user_root(base_runs_root, user_ctx.user_id)
    runs_root = user_runs_root(base_runs_root, user_ctx.user_id)
    runs_root.mkdir(parents=True, exist_ok=True)
    return user_ctx, base_runs_root, owner_root, runs_root, runs_check


def _mark_demo_runs(runs: list[dict[str, object]]) -> list[dict[str, object]]:
    for run in runs:
        run.setdefault("mode", "demo")
        if "id" in run and "run_id" not in run:
            run["run_id"] = run.get("id")
    return runs


def _load_manifest(run_dir: Path) -> dict[str, object]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_flags_from_present(run_dir: Path, artifacts_present: list[object]) -> dict[str, bool]:
    names = {str(name) for name in artifacts_present if isinstance(name, str)}
    has_trades = "trades.parquet" in names or "trades.jsonl" in names
    has_ohlcv = False
    for name in names:
        if name == "ohlcv.parquet" or name == "ohlcv_1m.parquet":
            has_ohlcv = True
            break
        if name.startswith("ohlcv_") and (name.endswith(".parquet") or name.endswith(".jsonl")):
            has_ohlcv = True
            break
    has_timeline = False
    for name in names:
        if name in {
            "timeline.json",
            "timeline_events.json",
            "risk_timeline.json",
            "selector_trace.json",
        }:
            has_timeline = True
            break
    if not has_timeline:
        has_timeline = find_timeline_path(run_dir) is not None
    return {
        "decisions": "decision_records.jsonl" in names,
        "trades": has_trades,
        "metrics": "metrics.json" in names,
        "ohlcv": has_ohlcv,
        "timeline": has_timeline,
        "risk_report": "risk_report.json" in names,
        "manifest": "manifest.json" in names,
    }


def _build_registry_run_list(runs_root: Path, runs: list[object]) -> list[dict[str, object]]:
    listings: list[dict[str, object]] = []
    for entry in runs:
        if not isinstance(entry, dict):
            continue
        run_id = str(entry.get("run_id") or "").strip()
        if not run_id:
            continue
        run_dir = (runs_root / run_id).resolve()
        if not is_within_root(run_dir, runs_root):
            continue
        manifest = _load_manifest(run_dir)
        manifest_data = manifest.get("data") if isinstance(manifest.get("data"), dict) else {}
        strategy = entry.get("strategy_id") or (manifest.get("strategy") or {}).get("id")
        symbol = entry.get("symbol") or (manifest_data or {}).get("symbol")
        timeframe = entry.get("timeframe") or (manifest_data or {}).get("timeframe")
        created_at = entry.get("created_at") or manifest.get("created_at")
        status = entry.get("status") or "UNKNOWN"
        health = entry.get("health") or ("CORRUPTED" if status == "CORRUPTED" else "UNKNOWN")
        artifacts_present = entry.get("artifacts_present")
        if not isinstance(artifacts_present, list):
            artifacts_present = []
        missing_artifacts = entry.get("missing_artifacts")
        if not isinstance(missing_artifacts, list):
            missing_artifacts = []
        invalid_artifacts = entry.get("invalid_artifacts")
        if not isinstance(invalid_artifacts, list):
            invalid_artifacts = []
        artifacts = _artifact_flags_from_present(run_dir, artifacts_present)
        listings.append(
            {
                "id": run_id,
                "run_id": run_id,
                "owner_user_id": entry.get("owner_user_id"),
                "path": str(run_dir),
                "created_at": created_at,
                "status": status,
                "health": health,
                "strategy": strategy,
                "symbols": [symbol] if symbol else None,
                "timeframe": timeframe,
                "has_trades": artifacts.get("trades", False),
                "artifacts": artifacts,
                "missing_artifacts": missing_artifacts,
                "invalid_artifacts": invalid_artifacts,
                "last_verified_at": entry.get("last_verified_at"),
                "meta": entry.get("meta") if isinstance(entry.get("meta"), dict) else {},
            }
        )
    return listings


def _normalize_artifact_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _diagnostics_payload(entry: dict[str, object]) -> dict[str, object]:
    run_id = str(entry.get("run_id") or "")
    status = str(entry.get("status") or "UNKNOWN")
    missing_artifacts = _normalize_artifact_list(entry.get("missing_artifacts"))
    invalid_artifacts = _normalize_artifact_list(entry.get("invalid_artifacts"))
    checks = entry.get("checks")
    if not isinstance(checks, dict):
        checks = {}

    health_raw = entry.get("health")
    health = str(health_raw).strip() if isinstance(health_raw, str) else ""
    if not health:
        if missing_artifacts:
            health = "CORRUPTED"
        elif invalid_artifacts:
            health = "DEGRADED"
        else:
            health = "HEALTHY"

    return {
        "run_id": run_id,
        "status": status,
        "health": health,
        "missing_artifacts": missing_artifacts,
        "invalid_artifacts": invalid_artifacts,
        "checks": checks,
        "artifacts_present": entry.get("artifacts_present")
        if isinstance(entry.get("artifacts_present"), list)
        else [],
        "last_verified_at": entry.get("last_verified_at"),
    }


def _invalid_run_id_response(run_id: str) -> JSONResponse:
    return error_response(400, "RUN_ID_INVALID", "Invalid run id", {"run_id": run_id})


def _resolve_registry_run_dir(
    user_root_path: Path,
    runs_root: Path,
    run_id: str,
    *,
    user_id: str,
) -> tuple[dict[str, object], Path] | JSONResponse:
    if _is_invalid_component(run_id):
        return _invalid_run_id_response(run_id)
    registry_result = _load_registry_with_lock(user_root_path)
    if isinstance(registry_result, JSONResponse):
        return registry_result
    entry = _find_registry_entry(registry_result, run_id)
    if entry is None:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    owner_user_id = str(entry.get("owner_user_id") or "").strip()
    if owner_user_id and owner_user_id != user_id:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    run_dir = (runs_root / run_id).resolve()
    if not is_within_root(run_dir, runs_root) or not run_dir.exists():
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    return entry, run_dir


def _resolve_run_dir_for_read(
    request: Request, run_id: str
) -> tuple[Path, str, str] | JSONResponse:
    user_ctx = _resolve_user_context(request)
    if isinstance(user_ctx, JSONResponse):
        return user_ctx

    readiness = _runs_root_readiness()
    if isinstance(readiness, JSONResponse):
        if _demo_mode_enabled():
            run_path = resolve_run_dir(run_id, get_artifacts_root())
            return run_path, "demo", user_ctx.user_id
        return readiness
    base_runs_root, _ = readiness
    user_root_path = user_root(base_runs_root, user_ctx.user_id)
    runs_root = user_runs_root(base_runs_root, user_ctx.user_id)
    runs_root.mkdir(parents=True, exist_ok=True)
    resolved = _resolve_registry_run_dir(
        user_root_path,
        runs_root,
        run_id,
        user_id=user_ctx.user_id,
    )
    if isinstance(resolved, JSONResponse):
        return resolved
    _, run_dir = resolved
    return run_dir, "runs_root", user_ctx.user_id


def _enrich_summary_with_manifest(
    summary: dict[str, object], run_path: Path, run_id: str
) -> dict[str, object]:
    manifest = _load_manifest(run_path)
    provenance_raw = summary.get("provenance")
    provenance = provenance_raw if isinstance(provenance_raw, dict) else {}

    manifest_strategy = manifest.get("strategy")
    strategy_obj = manifest_strategy if isinstance(manifest_strategy, dict) else {}
    manifest_risk = manifest.get("risk")
    risk_obj = manifest_risk if isinstance(manifest_risk, dict) else {}

    strategy_id = strategy_obj.get("id")
    if strategy_id is not None:
        provenance.setdefault("strategy_id", strategy_id)
    strategy_version = strategy_obj.get("version")
    if strategy_version is not None:
        provenance.setdefault("strategy_version", strategy_version)
    strategy_hash = _canonical_hash(strategy_obj if strategy_obj else strategy_id)
    if strategy_hash is not None:
        provenance.setdefault("strategy_hash", strategy_hash)

    risk_level = risk_obj.get("level")
    if isinstance(risk_level, int):
        provenance.setdefault("risk_level", risk_level)
    risk_config_hash = _canonical_hash(risk_obj if risk_obj else None)
    if risk_config_hash is not None:
        provenance.setdefault("risk_config_hash", risk_config_hash)

    stage_token = _resolve_stage_token(manifest)
    provenance.setdefault("stage_token", stage_token)
    provenance.setdefault("run_created_at", manifest.get("created_at"))

    summary["provenance"] = provenance
    summary["stage_token"] = stage_token

    risk_raw = summary.get("risk")
    risk = risk_raw if isinstance(risk_raw, dict) else {}
    if isinstance(risk_level, int):
        risk.setdefault("level", risk_level)
    if isinstance(risk, dict):
        summary["risk"] = risk

    summary.setdefault("run_id", run_id)
    return summary


def _build_export_bundle(run_path: Path, run_id: str) -> bytes:
    artifact_names = sorted([path.name for path in run_path.iterdir() if path.is_file()])
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name in artifact_names:
            path = run_path / name
            info = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
        manifest = {
            "run_id": run_id,
            "stage_token": STAGE_TOKEN,
            "artifacts": artifact_names,
        }
        info = zipfile.ZipInfo(
            filename="export_manifest.json",
            date_time=(1980, 1, 1, 0, 0, 0),
        )
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = 0o644 << 16
        archive.writestr(
            info,
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
    return stream.getvalue()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "api_version": API_VERSION}


@router.get("/health/ready")
def health_ready() -> dict[str, object]:
    runs_root_check, base_runs_root = _runs_root_readiness_check()
    checks: list[dict[str, object]] = [runs_root_check]
    if base_runs_root is not None:
        checks.extend(_readiness_registry_and_integrity_checks(base_runs_root))
    return _ready_payload(checks)


@router.get("/ready", response_model=None)
def ready() -> object:
    readiness = _runs_root_readiness()
    if isinstance(readiness, JSONResponse):
        return readiness
    base_runs_root, runs_check = readiness

    migration_check: dict[str, object] = {"status": "ok", "legacy_runs": 0}
    if has_legacy_runs(base_runs_root):
        default_user = (os.getenv(DEFAULT_USER_ENV) or "").strip()
        if not default_user:
            legacy_ids = [path.name for path in list_legacy_run_dirs(base_runs_root)]
            migration_check = {
                "status": "degraded",
                "code": "LEGACY_MIGRATION_REQUIRED",
                "legacy_runs": len(legacy_ids),
                "legacy_run_ids": legacy_ids,
                "message": f"Set {DEFAULT_USER_ENV} to migrate legacy runs",
            }
            return {
                "status": "degraded",
                "api_version": API_VERSION,
                "checks": {"runs_root": runs_check, "legacy_migration": migration_check},
            }
        try:
            migrated = migrate_legacy_runs(base_runs_root, default_user)
        except Exception as exc:
            migration_check = {
                "status": "degraded",
                "code": "LEGACY_MIGRATION_REQUIRED",
                "message": str(exc),
            }
            return {
                "status": "degraded",
                "api_version": API_VERSION,
                "checks": {"runs_root": runs_check, "legacy_migration": migration_check},
            }
        migration_check = {
            "status": "ok",
            "legacy_runs": 0,
            "migrated_runs": migrated.get("count", 0),
            "user_id": migrated.get("user_id"),
        }

    users_dir = base_runs_root / "users"
    users_dir.mkdir(parents=True, exist_ok=True)
    user_dirs = [path for path in users_dir.iterdir() if path.is_dir()]
    checks = {
        "runs_root": runs_check,
        "registry": {"status": "ok", "users": len(user_dirs)},
        "legacy_migration": migration_check,
    }
    return {"status": "ready", "api_version": API_VERSION, "checks": checks}


@router.get("/strategies")
def strategies() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for strategy in list_builtin_strategies():
        rows.append(
            {
                "id": strategy.get("id"),
                "display_name": strategy.get("display_name"),
                "description": strategy.get("description"),
                "param_schema": strategy.get("param_schema"),
                "default_params": strategy.get("default_params"),
                "tags": strategy.get("tags"),
            }
        )
    rows.sort(key=lambda item: str(item.get("id") or ""))
    return rows


@router.get("/data/imports")
def list_data_imports(request: Request) -> object:
    scope = _resolve_user_scope(request)
    if isinstance(scope, JSONResponse):
        return scope
    user_ctx, base_runs_root, _, _, _ = scope
    datasets = _list_datasets(base_runs_root, user_ctx.user_id)
    return {
        "datasets": datasets,
        "total": len(datasets),
        "timestamp": _utc_now_iso(),
        "stage_token": STAGE_TOKEN,
    }


@router.post("/data/import")
async def import_data(request: Request) -> JSONResponse:
    scope = _resolve_user_scope(request)
    if isinstance(scope, JSONResponse):
        return scope
    user_ctx, base_runs_root, _, _, _ = scope

    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        return error_response(
            400,
            "RUN_CONFIG_INVALID",
            "multipart/form-data file upload is required",
        )
    try:
        body = await request.body()
        parts = _parse_multipart_form(body, content_type)
    except Exception:
        return error_response(400, "RUN_CONFIG_INVALID", "Invalid multipart payload")

    file_part = parts.get("file")
    if not file_part or not isinstance(file_part.get("data"), (bytes, bytearray)):
        return error_response(400, "RUN_CONFIG_INVALID", "file is required")
    filename = str(file_part.get("filename") or "dataset.csv")

    try:
        dataset_id, manifest = _store_dataset_import(
            base_runs_root=base_runs_root,
            user_id=user_ctx.user_id,
            filename=filename,
            upload_bytes=bytes(file_part["data"]),
        )
    except RunBuilderError as exc:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)
    except Exception:
        return error_response(500, "INTERNAL", "Internal error")

    return JSONResponse(status_code=201, content={"dataset_id": dataset_id, "manifest": manifest})


@router.get("/runs")
def list_runs(request: Request) -> object:
    user_ctx = _resolve_user_context(request)
    if isinstance(user_ctx, JSONResponse):
        return user_ctx

    readiness = _runs_root_readiness()
    if isinstance(readiness, JSONResponse):
        if not _demo_mode_enabled():
            return readiness
        artifacts_root = get_artifacts_root()
        if not artifacts_root.exists():
            raise_api_error(
                404,
                "artifacts_root_missing",
                "Artifacts root not found",
                {"path": str(artifacts_root)},
            )
        runs = discover_runs()
        listings = _build_registry_run_list(artifacts_root, runs)
        return _mark_demo_runs(listings)

    base_runs_root, _ = readiness
    owner_root = user_root(base_runs_root, user_ctx.user_id)
    runs_root = user_runs_root(base_runs_root, user_ctx.user_id)
    runs_root.mkdir(parents=True, exist_ok=True)

    registry_result = _load_registry_with_lock(owner_root)
    if isinstance(registry_result, JSONResponse):
        return registry_result
    runs = registry_result.get("runs", []) if isinstance(registry_result, dict) else []
    return _build_registry_run_list(runs_root, runs if isinstance(runs, list) else [])


def _resolve_observability_scope(
    request: Request,
) -> tuple[UserContext, Path, Path, Path] | JSONResponse:
    user_ctx = _resolve_user_context(request)
    if isinstance(user_ctx, JSONResponse):
        return user_ctx
    readiness = _runs_root_readiness()
    if isinstance(readiness, JSONResponse):
        return readiness
    base_runs_root, _ = readiness
    owner_root = user_root(base_runs_root, user_ctx.user_id)
    runs_root = user_runs_root(base_runs_root, user_ctx.user_id)
    return user_ctx, base_runs_root, owner_root, runs_root


@router.get("/observability/runs")
def observability_runs(request: Request) -> object:
    scope = _resolve_observability_scope(request)
    if isinstance(scope, JSONResponse):
        return scope
    user_ctx, _, owner_root, runs_root = scope
    entries, metadata = _collect_registry_entries_read_only(
        owner_root,
        runs_root,
        user_id=user_ctx.user_id,
    )
    rows: list[dict[str, object]] = []
    for entry in entries:
        run_id = str(entry.get("run_id") or "").strip()
        if not run_id:
            continue
        run_dir = (runs_root / run_id).resolve()
        manifest = _load_manifest(run_dir) if run_dir.exists() else {}
        manifest_risk = manifest.get("risk") if isinstance(manifest.get("risk"), dict) else {}
        risk_level = manifest_risk.get("level")
        if not isinstance(risk_level, int):
            risk_level = None
        rows.append(
            {
                "run_id": run_id,
                "state": str(entry.get("status") or "UNKNOWN"),
                "strategy_id": entry.get("strategy_id")
                or (
                    (manifest.get("strategy") or {}).get("id")
                    if isinstance(manifest, dict)
                    else None
                ),
                "risk_level": risk_level,
                "created_at": entry.get("created_at") or manifest.get("created_at"),
                "updated_at": entry.get("last_verified_at"),
                "artifact_status": _artifact_status(entry),
                "validation_status": _validation_status(entry),
                "error_code": _error_code_for_entry(entry),
            }
        )
    return {
        "runs": rows,
        "total": len(rows),
        "timestamp": _utc_now_iso(),
        "stage_token": STAGE_TOKEN,
        "registry_error": metadata.get("registry_error"),
    }


@router.get("/observability/runs/{run_id}")
def observability_run_detail(run_id: str, request: Request) -> object:
    if _is_invalid_component(run_id):
        return _invalid_run_id_response(run_id)
    scope = _resolve_observability_scope(request)
    if isinstance(scope, JSONResponse):
        return scope
    user_ctx, _, owner_root, runs_root = scope
    entries, _ = _collect_registry_entries_read_only(
        owner_root, runs_root, user_id=user_ctx.user_id
    )
    by_id = {
        str(entry.get("run_id") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("run_id")
    }
    entry = by_id.get(run_id)
    if entry is None:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})

    run_dir = (runs_root / run_id).resolve()
    manifest = _load_manifest(run_dir) if run_dir.exists() and run_dir.is_dir() else {}
    provenance = _manifest_provenance(run_id, manifest, entry)
    envelope = _error_envelope_for_entry(run_id, entry, manifest)
    return {
        "run_id": run_id,
        "lifecycle": {
            "state": entry.get("status") or "UNKNOWN",
            "history": manifest.get("status_history")
            if isinstance(manifest.get("status_history"), list)
            else [],
        },
        "artifact_integrity": {
            "status": _artifact_status(entry),
            "missing_artifacts": _normalize_artifact_list(entry.get("missing_artifacts")),
            "invalid_artifacts": _normalize_artifact_list(entry.get("invalid_artifacts")),
            "checks": entry.get("checks") if isinstance(entry.get("checks"), dict) else {},
            "files": _artifact_digests(run_dir),
        },
        "validation": {
            "status": _validation_status(entry),
            "health": entry.get("health"),
            "last_verified_at": entry.get("last_verified_at"),
        },
        "error_envelope": envelope,
        "provenance": provenance,
    }


def _read_plugin_validation_failures(artifacts_root: Path) -> tuple[str, list[dict[str, object]]]:
    root = artifacts_root / "plugin_validation"
    if not root.exists() or not root.is_dir():
        return "empty", []

    failures: list[dict[str, object]] = []
    for plugin_type in ("indicator", "strategy"):
        folder = root / plugin_type
        if not folder.exists() or not folder.is_dir():
            continue
        for artifact_path in sorted(folder.glob("*.json"), key=lambda item: item.name):
            try:
                payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                failures.append(
                    {
                        "plugin_type": plugin_type,
                        "id": artifact_path.stem,
                        "status": "INVALID",
                        "error_envelope": build_error_envelope(
                            "PLUGIN_VALIDATION_ARTIFACT_INVALID",
                            "Plugin validation artifact invalid",
                            {
                                "artifact_reference": str(artifact_path),
                                "human_message": f"Invalid plugin validation artifact: {artifact_path.name}",
                                "run_id": None,
                            },
                        ),
                        "raw_error": str(exc),
                    }
                )
                continue
            if not isinstance(payload, dict):
                continue
            status = str(payload.get("status") or "INVALID").upper()
            if status == "VALID":
                continue
            plugin_id = str(payload.get("id") or artifact_path.stem)
            errors = payload.get("errors")
            first_error = errors[0] if isinstance(errors, list) and errors else {}
            if not isinstance(first_error, dict):
                first_error = {}
            rule_id = first_error.get("rule_id")
            message = first_error.get("message")
            failures.append(
                {
                    "plugin_type": plugin_type,
                    "id": plugin_id,
                    "status": status,
                    "error_envelope": build_error_envelope(
                        "PLUGIN_VALIDATION_FAILED",
                        f"Plugin validation failed for {plugin_id}",
                        {
                            "artifact_reference": str(artifact_path),
                            "human_message": str(message)
                            if isinstance(message, str) and message.strip()
                            else f"Plugin {plugin_id} failed validation.",
                            "run_id": None,
                            "strategy_id": plugin_id if plugin_type == "strategy" else None,
                            "stage_token": STAGE_TOKEN,
                        },
                    ),
                    "rule_id": rule_id if isinstance(rule_id, str) else None,
                    "artifact_path": str(artifact_path),
                }
            )
    status = "ok" if len(failures) == 0 else "degraded"
    return status, failures


@router.get("/observability/registry")
def observability_registry(request: Request) -> object:
    scope = _resolve_observability_scope(request)
    if isinstance(scope, JSONResponse):
        return scope
    user_ctx, _, owner_root, runs_root = scope
    entries, metadata = _collect_registry_entries_read_only(
        owner_root,
        runs_root,
        user_id=user_ctx.user_id,
    )
    corrupted = [
        str(entry.get("run_id"))
        for entry in entries
        if isinstance(entry, dict) and _artifact_status(entry) != "present"
    ]
    registry_error = metadata.get("registry_error")
    if isinstance(registry_error, str) and registry_error:
        registry_status = "corrupt"
    elif corrupted:
        registry_status = "degraded"
    else:
        registry_status = "healthy"

    plugin_status, failed_plugins = _read_plugin_validation_failures(get_artifacts_root())
    strategy_contract_versions: list[str] = []
    for failed in failed_plugins:
        envelope = failed.get("error_envelope")
        if not isinstance(envelope, dict):
            continue
        provenance = envelope.get("provenance")
        if not isinstance(provenance, dict):
            continue
        strategy = provenance.get("strategy")
        if not isinstance(strategy, dict):
            continue
        version = strategy.get("version")
        if isinstance(version, str) and version.strip():
            strategy_contract_versions.append(version)

    return {
        "registry_integrity_status": registry_status,
        "registry_error": registry_error,
        "corrupted_runs": corrupted,
        "plugin_load_status": plugin_status,
        "failed_plugins": failed_plugins,
        "contracts": {
            "strategy_contract_versions": sorted(set(strategy_contract_versions)),
            "risk_contract_versions_in_effect": ["v1"],
            "run_schema_version": "1.0.0",
        },
        "stage_token": STAGE_TOKEN,
        "timestamp": _utc_now_iso(),
    }


def _parse_multipart_form(body: bytes, content_type: str) -> dict[str, dict[str, object]]:
    header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
    message = BytesParser(policy=email_default).parsebytes(header + body)
    if not message.is_multipart():
        raise ValueError("Multipart payload expected")
    parts: dict[str, dict[str, object]] = {}
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        parts[name] = {
            "filename": part.get_filename(),
            "content_type": part.get_content_type(),
            "data": part.get_payload(decode=True) or b"",
        }
    return parts


def _store_uploaded_csv(upload_bytes: bytes, uploads_parent: Path) -> str:
    repo_root = Path.cwd().resolve()
    if not is_within_root(uploads_parent, repo_root):
        raise RunBuilderError(
            "RUN_CONFIG_INVALID",
            "RUNS_ROOT must be within repo for uploads",
            400,
            {"runs_root": str(uploads_parent)},
        )

    uploads_dir = uploads_parent
    uploads_dir.mkdir(parents=True, exist_ok=True)
    if not upload_bytes:
        raise RunBuilderError("RUN_CONFIG_INVALID", "Uploaded file is empty", 400)

    tmp_path = uploads_dir / f".tmp_upload_{uuid.uuid4().hex}.csv"
    digest = hashlib.sha256(upload_bytes).hexdigest()
    final_path = uploads_dir / f"{digest}.csv"
    if final_path.exists():
        return final_path.relative_to(repo_root).as_posix()

    try:
        tmp_path.write_bytes(upload_bytes)
    except OSError as exc:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise RunBuilderError(
            "ARTIFACTS_WRITE_FAILED",
            f"Failed to store upload: {exc}",
            500,
        ) from exc
    if not is_within_root(final_path, repo_root):
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise RunBuilderError(
            "RUN_CONFIG_INVALID",
            "Upload path resolved outside repo",
            400,
        )

    os.replace(tmp_path, final_path)

    return final_path.relative_to(repo_root).as_posix()


def _repo_relative_path(path: Path) -> str:
    repo_root = Path.cwd().resolve()
    resolved = path.resolve()
    if not is_within_root(resolved, repo_root):
        raise RunBuilderError(
            "RUN_CONFIG_INVALID",
            "RUNS_ROOT must be within repo for local imports",
            400,
            {"path": str(resolved)},
        )
    return resolved.relative_to(repo_root).as_posix()


def _ensure_repo_dataset_cache(content_hash: str, upload_bytes: bytes) -> str:
    repo_root = Path.cwd().resolve()
    cache_root = (repo_root / ".runs_import_cache").resolve()
    if not is_within_root(cache_root, repo_root):
        raise RunBuilderError(
            "RUN_CONFIG_INVALID",
            "Import cache path is invalid",
            400,
            {"path": str(cache_root)},
        )
    cache_root.mkdir(parents=True, exist_ok=True)
    cached_path = (cache_root / f"{content_hash}.csv").resolve()
    if not is_within_root(cached_path, cache_root):
        raise RunBuilderError(
            "RUN_CONFIG_INVALID",
            "Import cache path is invalid",
            400,
            {"path": str(cached_path)},
        )
    if not cached_path.exists():
        try:
            cached_path.write_bytes(upload_bytes)
        except OSError as exc:
            raise RunBuilderError(
                "ARTIFACTS_WRITE_FAILED",
                f"Failed to write import cache: {exc}",
                500,
            ) from exc
    return cached_path.relative_to(repo_root).as_posix()


def _dataset_paths(
    *,
    base_runs_root: Path,
    user_id: str,
    dataset_id: str,
) -> tuple[Path, Path, Path]:
    imports_root = user_imports_root(base_runs_root, user_id)
    dataset_dir = (imports_root / dataset_id).resolve()
    if not is_within_root(dataset_dir, imports_root.resolve()):
        raise RunBuilderError("RUN_CONFIG_INVALID", "dataset_id is invalid", 400)
    dataset_path = (dataset_dir / "dataset.csv").resolve()
    manifest_path = (dataset_dir / "manifest.json").resolve()
    return dataset_dir, dataset_path, manifest_path


def _normalize_dataset_id(raw: object) -> str:
    dataset_id = str(raw or "").strip().lower()
    if not DATASET_ID_PATTERN.match(dataset_id):
        raise RunBuilderError("RUN_CONFIG_INVALID", "dataset_id is invalid", 400)
    return dataset_id


def _read_dataset_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _list_datasets(base_runs_root: Path, user_id: str) -> list[dict[str, object]]:
    imports_root = user_imports_root(base_runs_root, user_id)
    if not imports_root.exists() or not imports_root.is_dir():
        return []

    manifests: list[dict[str, object]] = []
    for dataset_dir in sorted(imports_root.iterdir(), key=lambda item: item.name):
        if not dataset_dir.is_dir():
            continue
        manifest = _read_dataset_manifest(dataset_dir / "manifest.json")
        content_hash = str(manifest.get("content_hash") or "").strip().lower()
        if not DATASET_ID_PATTERN.match(content_hash):
            continue
        manifests.append(manifest)
    manifests.sort(key=lambda item: str(item.get("content_hash") or ""))
    return manifests


def _store_dataset_import(
    *,
    base_runs_root: Path,
    user_id: str,
    filename: str,
    upload_bytes: bytes,
) -> tuple[str, dict[str, object]]:
    if not upload_bytes:
        raise RunBuilderError("DATA_INVALID", "Uploaded CSV is empty", 400)
    if len(upload_bytes) > DATASET_MAX_BYTES:
        raise RunBuilderError(
            "DATA_INVALID",
            "Uploaded CSV is too large",
            400,
            {"max_bytes": DATASET_MAX_BYTES},
        )

    content_hash = hashlib.sha256(upload_bytes).hexdigest()
    dataset_dir, dataset_path, manifest_path = _dataset_paths(
        base_runs_root=base_runs_root,
        user_id=user_id,
        dataset_id=content_hash,
    )
    dataset_dir.mkdir(parents=True, exist_ok=True)
    wrote_dataset = False
    if not dataset_path.exists():
        dataset_path.write_bytes(upload_bytes)
        wrote_dataset = True

    try:
        try:
            source_path = _repo_relative_path(dataset_path)
        except RunBuilderError:
            source_path = _ensure_repo_dataset_cache(content_hash, upload_bytes)
        inspection = inspect_csv_path(source_path)
    except Exception:
        if wrote_dataset:
            try:
                dataset_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    inferred = inspection.get("inferred_time_range")
    inferred_time_range = inferred if isinstance(inferred, dict) else {}
    manifest: dict[str, object] = {
        "content_hash": content_hash,
        "filename": filename or "dataset.csv",
        "row_count": int(inspection.get("row_count") or 0),
        "columns": inspection.get("columns") if isinstance(inspection.get("columns"), list) else [],
        "inferred_time_range": inferred_time_range,
        "source_path": source_path,
        "storage_path": str(dataset_path),
        "imported_at": _utc_now_iso(),
        "stage_token": STAGE_TOKEN,
    }
    write_canonical_json(manifest_path, manifest)
    return content_hash, manifest


def _normalize_product_run_payload(
    payload: dict[str, object],
    *,
    base_runs_root: Path,
    user_id: str,
) -> tuple[dict[str, object], str]:
    dataset_id = _normalize_dataset_id(payload.get("dataset_id"))
    strategy_id = str(payload.get("strategy_id") or "").strip()
    params = payload.get("params")
    if params is None:
        params = {}
    risk_level = payload.get("risk_level")
    try:
        risk_level_int = int(risk_level)
    except (TypeError, ValueError) as exc:
        raise RunBuilderError("RISK_INVALID", "risk_level must be an integer", 400) from exc
    if risk_level_int < 1 or risk_level_int > 5:
        raise RunBuilderError("RISK_INVALID", "risk_level must be 1..5", 400)

    _, dataset_path, manifest_path = _dataset_paths(
        base_runs_root=base_runs_root,
        user_id=user_id,
        dataset_id=dataset_id,
    )
    manifest = _read_dataset_manifest(manifest_path)
    if not dataset_path.exists() or not manifest:
        raise RunBuilderError(
            "DATA_SOURCE_NOT_FOUND",
            "dataset_id not found",
            400,
            {"dataset_id": dataset_id},
        )

    source_path = manifest.get("source_path")
    if not isinstance(source_path, str) or not source_path.strip():
        try:
            source_path = _repo_relative_path(dataset_path)
        except RunBuilderError:
            source_path = _ensure_repo_dataset_cache(dataset_id, dataset_path.read_bytes())

    strategy_payload = {"id": strategy_id, "params": params}
    normalized_strategy_id, normalized_params = normalize_strategy_request(strategy_payload)
    normalized = {
        "schema_version": "1.0.0",
        "data_source": {
            "type": "csv",
            "path": source_path,
            "symbol": DATASET_DEFAULT_SYMBOL,
            "timeframe": DATASET_DEFAULT_TIMEFRAME,
        },
        "strategy": {"id": normalized_strategy_id, "params": normalized_params},
        "risk": {"level": risk_level_int},
        "costs": {"commission_bps": 0.0, "slippage_bps": 0.0},
    }
    return normalized, dataset_id


def _status_percent(state: str) -> int:
    normalized = (state or "").strip().upper()
    if normalized in {"COMPLETED", "OK", "FAILED", "CORRUPTED"}:
        return 100
    if normalized == "RUNNING":
        return 70
    if normalized == "VALIDATED":
        return 35
    if normalized == "CREATED":
        return 10
    return 0


@router.post("/runs")
async def create_run_endpoint(request: Request) -> JSONResponse:
    if _kill_switch_enabled():
        return error_response(
            503,
            "KILL_SWITCH_ENABLED",
            "Run creation disabled",
            {"env": KILL_SWITCH_ENV},
        )
    user_ctx = _resolve_user_context(request)
    if isinstance(user_ctx, JSONResponse):
        return user_ctx

    content_type = request.headers.get("content-type", "")
    if content_type.lower().startswith("multipart/form-data"):
        try:
            body = await request.body()
            parts = _parse_multipart_form(body, content_type)
        except Exception:
            return error_response(400, "RUN_CONFIG_INVALID", "Invalid multipart payload")
        file_part = parts.get("file")
        request_part = parts.get("request")
        if not file_part or not isinstance(file_part.get("data"), (bytes, bytearray)):
            return error_response(400, "RUN_CONFIG_INVALID", "file is required")
        if not request_part or not isinstance(request_part.get("data"), (bytes, bytearray)):
            return error_response(400, "RUN_CONFIG_INVALID", "request is required")
        try:
            payload = json.loads(request_part["data"].decode("utf-8"))
        except Exception:
            return error_response(400, "RUN_CONFIG_INVALID", "Invalid request JSON")

        readiness = _runs_root_readiness()
        if isinstance(readiness, JSONResponse):
            return readiness
        base_runs_root, _ = readiness
        try:
            upload_root = user_uploads_root(base_runs_root, user_ctx.user_id)
            upload_path = _store_uploaded_csv(bytes(file_part["data"]), upload_root)
        except RunBuilderError as exc:
            return error_response(exc.status_code, exc.code, exc.message, exc.details)
        if not isinstance(payload, dict):
            payload = {}
        data_source = payload.get("data_source")
        if not isinstance(data_source, dict):
            data_source = {}
            payload["data_source"] = data_source
        data_source.setdefault("type", "csv")
        data_source["path"] = upload_path
    else:
        try:
            payload = await request.json()
        except Exception:
            return error_response(400, "RUN_CONFIG_INVALID", "Invalid JSON payload")

    is_product_payload = isinstance(payload, dict) and any(
        key in payload for key in ("dataset_id", "strategy_id", "risk_level")
    )

    try:
        if is_product_payload:
            readiness = _runs_root_readiness()
            if isinstance(readiness, JSONResponse):
                return readiness
            base_runs_root, _ = readiness
            normalized_payload, _ = _normalize_product_run_payload(
                payload,
                base_runs_root=base_runs_root,
                user_id=user_ctx.user_id,
            )
            status_code, response = create_run(normalized_payload, user_id=user_ctx.user_id)
            run_id = str(response.get("run_id") or "").strip()
            if not run_id:
                return error_response(500, "INTERNAL", "Internal error")

            runs_root = user_runs_root(base_runs_root, user_ctx.user_id)
            run_dir = (runs_root / run_id).resolve()
            manifest = _load_manifest(run_dir)
            provenance = _manifest_provenance(
                run_id,
                manifest,
                {
                    "strategy_id": (normalized_payload.get("strategy") or {}).get("id"),
                    "risk_level": (normalized_payload.get("risk") or {}).get("level"),
                    "status": response.get("status"),
                },
            )
            return JSONResponse(
                status_code=status_code,
                content={
                    "run_id": run_id,
                    "status": response.get("status"),
                    "provenance": provenance,
                },
            )

        status_code, response = create_run(payload, user_id=user_ctx.user_id)
        return JSONResponse(status_code=status_code, content=response)
    except RunBuilderError as exc:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)
    except Exception:
        return error_response(500, "INTERNAL", "Internal error")


@router.get("/runs/{run_id}/status")
def run_status(run_id: str, request: Request) -> object:
    scope = _resolve_user_scope(request)
    if isinstance(scope, JSONResponse):
        return scope
    user_ctx, _, owner_root, runs_root, _ = scope
    if _is_invalid_component(run_id):
        return _invalid_run_id_response(run_id)

    registry_result = _load_registry_with_lock(owner_root)
    if isinstance(registry_result, JSONResponse):
        return registry_result
    entry = _find_registry_entry(registry_result, run_id)
    if entry is None:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})

    owner_user_id = str(entry.get("owner_user_id") or "").strip()
    if owner_user_id and owner_user_id != user_ctx.user_id:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})

    run_dir = (runs_root / run_id).resolve()
    manifest = _load_manifest(run_dir) if run_dir.exists() and run_dir.is_dir() else {}
    lifecycle = (
        manifest.get("status_history") if isinstance(manifest.get("status_history"), list) else []
    )
    state = str(entry.get("status") or "UNKNOWN")
    last_stage = str(lifecycle[-1] if lifecycle else state)
    last_event: dict[str, object] = {
        "stage": last_stage,
        "timestamp": manifest.get("created_at") if isinstance(manifest, dict) else None,
        "detail": f"status={last_stage}",
    }

    if run_dir.exists() and run_dir.is_dir():
        timeline_path = find_timeline_path(run_dir)
        if timeline_path is not None:
            try:
                events = load_timeline(timeline_path)
            except RuntimeError:
                events = []
            if events:
                tail = events[-1] if isinstance(events[-1], dict) else {}
                last_event = {
                    "stage": tail.get("stage") or tail.get("title") or last_stage,
                    "timestamp": tail.get("timestamp") or manifest.get("created_at"),
                    "detail": tail.get("detail") or tail.get("title") or f"status={last_stage}",
                }

    payload: dict[str, object] = {
        "state": state,
        "percent": _status_percent(state),
        "last_event": last_event,
    }
    envelope = _error_envelope_for_entry(run_id, entry, manifest)
    if envelope is not None:
        payload["error_envelope"] = envelope
    return payload


@router.get("/runs/{run_id}/manifest")
def run_manifest(run_id: str, request: Request) -> JSONResponse:
    scope = _resolve_user_scope(request)
    if isinstance(scope, JSONResponse):
        return scope
    user_ctx, _, owner_root, runs_root, _ = scope
    invalid = _is_invalid_component(run_id)
    if invalid:
        return _invalid_run_id_response(run_id)

    registry_result = _load_registry_with_lock(owner_root)
    if isinstance(registry_result, JSONResponse):
        return registry_result
    entry = _find_registry_entry(registry_result, run_id)
    if entry is None:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    owner_user_id = str(entry.get("owner_user_id") or "").strip()
    if owner_user_id and owner_user_id != user_ctx.user_id:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    if entry.get("status") == "CORRUPTED":
        return error_response(409, "RUN_CORRUPTED", "Run artifacts missing", {"run_id": run_id})

    run_dir = (runs_root / run_id).resolve()
    if not is_within_root(run_dir, runs_root) or not run_dir.exists():
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return error_response(409, "RUN_CORRUPTED", "Run artifacts missing", {"run_id": run_id})

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return error_response(409, "RUN_CORRUPTED", "Manifest invalid", {"run_id": run_id})
    return JSONResponse(status_code=200, content=payload)


@router.get("/runs/{run_id}/artifacts/{name}", response_model=None)
def run_artifact(run_id: str, name: str, request: Request):
    scope = _resolve_user_scope(request)
    if isinstance(scope, JSONResponse):
        return scope
    user_ctx, _, owner_root, runs_root, _ = scope
    if _is_invalid_component(run_id):
        return _invalid_run_id_response(run_id)
    if _is_invalid_component(name):
        return error_response(400, "RUN_CONFIG_INVALID", "Invalid artifact name", {"name": name})

    registry_result = _load_registry_with_lock(owner_root)
    if isinstance(registry_result, JSONResponse):
        return registry_result
    entry = _find_registry_entry(registry_result, run_id)
    if entry is None:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    owner_user_id = str(entry.get("owner_user_id") or "").strip()
    if owner_user_id and owner_user_id != user_ctx.user_id:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    if entry.get("status") == "CORRUPTED":
        return error_response(409, "RUN_CORRUPTED", "Run artifacts missing", {"run_id": run_id})

    run_dir = (runs_root / run_id).resolve()
    if not is_within_root(run_dir, runs_root) or not run_dir.exists():
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})

    artifact_path = (run_dir / name).resolve()
    if not is_within_root(artifact_path, run_dir) or not artifact_path.exists():
        return error_response(
            404,
            "ARTIFACT_NOT_FOUND",
            "Artifact not found",
            {"run_id": run_id, "name": name},
        )

    media_type = _artifact_media_type(name)
    try:
        content = artifact_path.read_bytes()
    except OSError:
        return error_response(
            404,
            "ARTIFACT_NOT_FOUND",
            "Artifact not found",
            {"run_id": run_id, "name": name},
        )
    return StreamingResponse(iter([content]), media_type=media_type)


@router.get("/runs/{run_id}/diagnostics")
def run_diagnostics(run_id: str, request: Request) -> object:
    user_ctx = _resolve_user_context(request)
    if isinstance(user_ctx, JSONResponse):
        return user_ctx

    readiness = _runs_root_readiness()
    if isinstance(readiness, JSONResponse):
        if not _demo_mode_enabled():
            return readiness
        run_path = resolve_run_dir(run_id, get_artifacts_root())
        manifest = _load_manifest(run_path)
        payload = _diagnostics_payload(
            build_registry_entry(run_path, manifest, user_id=user_ctx.user_id)
        )
        payload["mode"] = "demo"
        return payload

    base_runs_root, _ = readiness
    owner_root = user_root(base_runs_root, user_ctx.user_id)
    runs_root = user_runs_root(base_runs_root, user_ctx.user_id)
    runs_root.mkdir(parents=True, exist_ok=True)
    if _is_invalid_component(run_id):
        return _invalid_run_id_response(run_id)

    registry_result = _load_registry_with_lock(owner_root)
    if isinstance(registry_result, JSONResponse):
        return registry_result
    entry = _find_registry_entry(registry_result, run_id)
    if entry is None:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    owner_user_id = str(entry.get("owner_user_id") or "").strip()
    if owner_user_id and owner_user_id != user_ctx.user_id:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    return _diagnostics_payload(entry)


@router.get("/plugins/active")
def list_active() -> dict[str, list[dict[str, object]]]:
    return list_active_plugins(get_artifacts_root())


@router.get("/plugins/failed")
def list_failed() -> dict[str, list[dict[str, object]]]:
    return list_failed_plugins(get_artifacts_root())


@router.get("/plugins/validation-summary")
def validation_summary() -> dict[str, object]:
    return get_validation_summary(get_artifacts_root())


@router.get("/runs/{run_id}/summary")
def run_summary(run_id: str, request: Request) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode, _ = resolved
    decision_path = run_path / "decision_records.jsonl"
    if not decision_path.exists():
        raise_api_error(
            404,
            "decision_records_missing",
            "decision_records.jsonl missing",
            {"run_id": run_id},
        )
    validation = validate_decision_records(decision_path)
    if validation:
        raise_api_error(
            422,
            "decision_records_invalid",
            "decision_records.jsonl contains invalid JSON lines",
            validation,
        )
    summary = dict(build_summary(decision_path))
    summary["run_id"] = run_id
    summary["artifacts"] = collect_run_artifacts(run_path)
    summary = _enrich_summary_with_manifest(summary, run_path, run_id)
    if mode == "demo":
        summary["mode"] = "demo"
    return summary


@router.get("/runs/{run_id}/decisions")
def decisions(
    run_id: str,
    request: Request,
    symbol: list[str] | None = Query(default=None),
    action: list[str] | None = Query(default=None),
    severity: list[str] | None = Query(default=None),
    reason_code: list[str] | None = Query(default=None),
    start_ts: str | None = None,
    end_ts: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode, _ = resolved
    decision_path = run_path / "decision_records.jsonl"
    if not decision_path.exists():
        raise_api_error(
            404,
            "decision_records_missing",
            "decision_records.jsonl missing",
            {"run_id": run_id},
        )
    validation = validate_decision_records(decision_path)
    if validation:
        raise_api_error(
            422,
            "decision_records_invalid",
            "decision_records.jsonl contains invalid JSON lines",
            validation,
        )

    symbol = _normalize_filter_values(symbol, "symbol")
    action = _normalize_filter_values(action, "action")
    severity = _normalize_filter_values(severity, "severity")
    reason_code = _normalize_filter_values(reason_code, "reason_code")

    start_dt, end_dt = _parse_time_range(start_ts, end_ts)

    payload = filter_decisions(
        decision_path,
        symbol,
        action,
        severity,
        reason_code,
        start_dt,
        end_dt,
        page,
        page_size,
    )
    if mode == "demo":
        payload["mode"] = "demo"
    return payload


@router.get("/runs/{run_id}/trades")
def trades(
    run_id: str,
    request: Request,
    start_ts: str | None = None,
    end_ts: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode, _ = resolved
    trade_parquet_path = run_path / "trades.parquet"
    trade_jsonl_path = run_path / "trades.jsonl"
    if trade_parquet_path.exists():
        trade_path = trade_parquet_path
        trade_loader = load_trades
    elif trade_jsonl_path.exists():
        trade_path = trade_jsonl_path
        trade_loader = load_trades_jsonl
    else:
        raise_api_error(404, "trades_missing", "trades artifact missing", {"run_id": run_id})

    start_dt, end_dt = _parse_time_range(start_ts, end_ts)

    try:
        payload = trade_loader(trade_path, start_dt, end_dt, page, page_size)
    except RuntimeError as exc:
        raise_api_error(422, "trades_invalid", str(exc), {"run_id": run_id})
    if mode == "demo":
        payload["mode"] = "demo"
    return payload


@router.get("/runs/{run_id}/trades/markers")
def trade_markers(
    run_id: str,
    request: Request,
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode, _ = resolved
    trade_parquet_path = run_path / "trades.parquet"
    trade_jsonl_path = run_path / "trades.jsonl"
    if trade_parquet_path.exists():
        trade_path = trade_parquet_path
        marker_loader = load_trade_markers
    elif trade_jsonl_path.exists():
        trade_path = trade_jsonl_path
        marker_loader = load_trade_markers_jsonl
    else:
        raise_api_error(404, "trades_missing", "trades artifact missing", {"run_id": run_id})

    start_dt, end_dt = _parse_time_range(start_ts, end_ts)
    try:
        payload = marker_loader(trade_path, start_ts=start_dt, end_ts=end_dt)
    except RuntimeError as exc:
        raise_api_error(422, "trades_invalid", str(exc), {"run_id": run_id})
    payload["run_id"] = run_id
    if mode == "demo":
        payload["mode"] = "demo"
    return payload


@router.get("/runs/{run_id}/ohlcv")
def ohlcv(
    run_id: str,
    request: Request,
    symbol: str | None = None,
    timeframe: str | None = None,
    start_ts: str | None = None,
    end_ts: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=10000),
) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode, _ = resolved
    ohlcv_path = resolve_ohlcv_path(run_path, timeframe)
    if ohlcv_path is not None:
        ohlcv_loader = load_ohlcv
        source_path = ohlcv_path
    else:
        ohlcv_jsonl_path = resolve_ohlcv_jsonl_path(run_path, timeframe)
        if ohlcv_jsonl_path is None:
            raise_api_error(
                404,
                "ohlcv_missing",
                "OHLCV artifact missing",
                {"run_id": run_id, "timeframe": timeframe},
            )
        ohlcv_loader = load_ohlcv_jsonl
        source_path = ohlcv_jsonl_path

    start_dt, end_dt = _parse_time_range(start_ts, end_ts)
    try:
        payload = ohlcv_loader(source_path, start_ts=start_dt, end_ts=end_dt, limit=limit)
    except RuntimeError as exc:
        raise_api_error(
            422,
            "ohlcv_invalid",
            str(exc),
            {"run_id": run_id, "timeframe": timeframe},
        )
    payload["run_id"] = run_id
    payload["symbol"] = symbol
    payload["timeframe"] = timeframe
    payload["source"] = source_path.name
    if mode == "demo":
        payload["mode"] = "demo"
    return payload


@router.get("/runs/{run_id}/metrics")
def metrics(run_id: str, request: Request) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode, _ = resolved
    metrics_path = run_path / "metrics.json"
    if not metrics_path.exists():
        raise_api_error(404, "metrics_missing", "metrics.json missing", {"run_id": run_id})
    try:
        payload = load_metrics(metrics_path)
    except RuntimeError as exc:
        raise_api_error(422, "metrics_invalid", str(exc), {"run_id": run_id})
    payload.setdefault("run_id", run_id)
    if mode == "demo":
        payload["mode"] = "demo"
    return payload


@router.get("/runs/{run_id}/timeline")
def timeline(run_id: str, request: Request, source: str = "auto") -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode, _ = resolved
    source_key = (source or "auto").lower()
    timeline_path = None

    if source_key in {"auto", "artifact"}:
        timeline_path = find_timeline_path(run_path)
        if timeline_path is None and source_key == "artifact":
            raise_api_error(
                404,
                "timeline_missing",
                "timeline artifact missing",
                {"run_id": run_id},
            )

    if timeline_path is not None:
        try:
            events = load_timeline(timeline_path)
        except RuntimeError as exc:
            raise_api_error(422, "timeline_invalid", str(exc), {"run_id": run_id})
    else:
        decision_path = run_path / "decision_records.jsonl"
        if not decision_path.exists():
            raise_api_error(
                404,
                "decision_records_missing",
                "decision_records.jsonl missing",
                {"run_id": run_id},
            )
        validation = validate_decision_records(decision_path)
        if validation:
            raise_api_error(
                422,
                "decision_records_invalid",
                "decision_records.jsonl contains invalid JSON lines",
                validation,
            )
        events = build_timeline_from_decisions(decision_path)

    payload = {"run_id": run_id, "total": len(events), "events": events}
    if mode == "demo":
        payload["mode"] = "demo"
    return payload


@router.get("/runs/{run_id}/errors")
def errors(run_id: str, request: Request) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode, _ = resolved
    decision_path = run_path / "decision_records.jsonl"
    if not decision_path.exists():
        raise_api_error(
            404,
            "decision_records_missing",
            "decision_records.jsonl missing",
            {"run_id": run_id},
        )
    validation = validate_decision_records(decision_path)
    if validation:
        raise_api_error(
            422,
            "decision_records_invalid",
            "decision_records.jsonl contains invalid JSON lines",
            validation,
        )
    payload = collect_error_records(decision_path)
    if mode == "demo":
        payload["mode"] = "demo"
    return payload


@router.get("/runs/{run_id}/decisions/export")
def export_decisions(
    run_id: str,
    request: Request,
    format: str = "json",
    symbol: list[str] | None = Query(default=None),
    action: list[str] | None = Query(default=None),
    severity: list[str] | None = Query(default=None),
    reason_code: list[str] | None = Query(default=None),
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> StreamingResponse:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, _, _ = resolved
    decision_path = run_path / "decision_records.jsonl"
    if not decision_path.exists():
        raise_api_error(
            404,
            "decision_records_missing",
            "decision_records.jsonl missing",
            {"run_id": run_id},
        )
    validation = validate_decision_records(decision_path)
    if validation:
        raise_api_error(
            422,
            "decision_records_invalid",
            "decision_records.jsonl contains invalid JSON lines",
            validation,
        )

    symbol = _normalize_filter_values(symbol, "symbol")
    action = _normalize_filter_values(action, "action")
    severity = _normalize_filter_values(severity, "severity")
    reason_code = _normalize_filter_values(reason_code, "reason_code")

    start_dt, end_dt = _parse_time_range(start_ts, end_ts)
    try:
        stream, media_type = stream_decisions_export(
            decision_path,
            symbols=symbol,
            actions=action,
            severities=severity,
            reason_codes=reason_code,
            start_ts=start_dt,
            end_ts=end_dt,
            fmt=format,
        )
    except ValueError as exc:
        raise_api_error(400, "invalid_export_format", str(exc), {"run_id": run_id})
    return _export_response(stream, media_type, f"{run_id}-decisions.{format}")


@router.get("/runs/{run_id}/errors/export")
def export_errors(run_id: str, request: Request, format: str = "json") -> StreamingResponse:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, _, _ = resolved
    decision_path = run_path / "decision_records.jsonl"
    if not decision_path.exists():
        raise_api_error(
            404,
            "decision_records_missing",
            "decision_records.jsonl missing",
            {"run_id": run_id},
        )
    validation = validate_decision_records(decision_path)
    if validation:
        raise_api_error(
            422,
            "decision_records_invalid",
            "decision_records.jsonl contains invalid JSON lines",
            validation,
        )

    try:
        stream, media_type = stream_errors_export(decision_path, fmt=format)
    except ValueError as exc:
        raise_api_error(400, "invalid_export_format", str(exc), {"run_id": run_id})
    return _export_response(stream, media_type, f"{run_id}-errors.{format}")


@router.get("/runs/{run_id}/trades/export")
def export_trades(
    run_id: str,
    request: Request,
    format: str = "json",
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> StreamingResponse:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, _, _ = resolved
    trade_parquet_path = run_path / "trades.parquet"
    trade_jsonl_path = run_path / "trades.jsonl"
    if trade_parquet_path.exists():
        trade_path = trade_parquet_path
    elif trade_jsonl_path.exists():
        trade_path = trade_jsonl_path
    else:
        raise_api_error(404, "trades_missing", "trades artifact missing", {"run_id": run_id})

    start_dt, end_dt = _parse_time_range(start_ts, end_ts)
    try:
        stream, media_type = stream_trades_export(
            trade_path, start_ts=start_dt, end_ts=end_dt, fmt=format
        )
    except ValueError as exc:
        raise_api_error(400, "invalid_export_format", str(exc), {"run_id": run_id})
    return _export_response(stream, media_type, f"{run_id}-trades.{format}")


@router.get("/runs/{run_id}/report/export", response_model=None)
def export_report_bundle(run_id: str, request: Request) -> StreamingResponse:
    resolved = _resolve_run_dir_for_read(request, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, _, _ = resolved
    bundle = _build_export_bundle(run_path, run_id)
    headers = {
        "Content-Disposition": f'attachment; filename="{run_id}-report.zip"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(iter([bundle]), media_type="application/zip", headers=headers)


app = FastAPI(title="Buff Artifacts API", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api", include_in_schema=False)
app.include_router(router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api", include_in_schema=False)
app.include_router(chat_router, prefix="/api/v1")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and {"code", "message", "details"}.issubset(exc.detail):
        return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)
    payload = build_error_payload(
        "http_error",
        str(exc.detail),
        {"detail": exc.detail},
    )
    return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    payload = build_error_payload(
        "validation_error",
        "Request validation failed",
        {"errors": exc.errors()},
    )
    return JSONResponse(status_code=422, content=payload)


def _parse_time_range(
    start_ts: str | None, end_ts: str | None
) -> tuple[datetime | None, datetime | None]:
    start_dt = coerce_ts_param(start_ts, "start_ts")
    end_dt = coerce_ts_param(end_ts, "end_ts")
    if start_dt and end_dt and start_dt > end_dt:
        raise_api_error(
            400,
            "invalid_time_range",
            "start_ts must be <= end_ts",
            {"start_ts": start_ts, "end_ts": end_ts},
        )
    return start_dt, end_dt


def _normalize_filter_values(values: list[str] | None, name: str) -> list[str] | None:
    if not values:
        return None
    normalized: list[str] = []
    for value in values:
        if value is None:
            continue
        for item in str(value).split(","):
            item = item.strip()
            if item:
                normalized.append(item)
    if len(normalized) > 50:
        raise_api_error(
            400,
            "too_many_filter_values",
            f"{name} supports at most 50 values",
            {"name": name, "count": len(normalized)},
        )
    return normalized or None


def _export_response(stream: Iterable[bytes], media_type: str, filename: str) -> StreamingResponse:
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(stream, media_type=media_type, headers=headers)


def _load_registry_with_lock(user_root_path: Path) -> dict[str, object] | JSONResponse:
    lock = lock_registry(user_root_path)
    try:
        with lock:
            return reconcile_registry(user_root_path)
    except TimeoutError:
        return error_response(503, "REGISTRY_LOCK_TIMEOUT", "Registry lock timeout")
    except Exception:
        return error_response(500, "REGISTRY_WRITE_FAILED", "Registry write failed")


def _find_registry_entry(registry: dict[str, object], run_id: str) -> dict[str, object] | None:
    runs = registry.get("runs") if isinstance(registry, dict) else None
    if not isinstance(runs, list):
        return None
    for entry in runs:
        if isinstance(entry, dict) and entry.get("run_id") == run_id:
            return entry
    return None


def _is_invalid_component(value: str) -> bool:
    candidate = (value or "").strip()
    if not is_valid_component(candidate):
        return True
    return candidate.startswith(".")


def _artifact_media_type(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".jsonl") or lowered.endswith(".ndjson"):
        return "application/x-ndjson; charset=utf-8"
    if lowered.endswith(".json"):
        return "application/json; charset=utf-8"
    return "text/plain; charset=utf-8"
