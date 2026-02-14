from __future__ import annotations

import hashlib
import json
import os
import uuid
from email.parser import BytesParser
from email.policy import default as email_default
from datetime import datetime
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
from .errors import build_error_payload, raise_api_error
from .plugins import get_validation_summary, list_active_plugins, list_failed_plugins
from .timeutils import coerce_ts_param
from .phase6.http import error_response
from .phase6.paths import RUNS_ROOT_ENV, get_runs_root, is_within_root
from .phase6.registry import lock_registry, reconcile_registry
from .phase6.run_builder import RunBuilderError, create_run

router = APIRouter()
KILL_SWITCH_ENV = "BUFF_KILL_SWITCH"
DEMO_MODE_ENV = "DEMO_MODE"


def _kill_switch_enabled() -> bool:
    return os.getenv(KILL_SWITCH_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _demo_mode_enabled() -> bool:
    return os.getenv(DEMO_MODE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


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
    return {
        "decisions": "decision_records.jsonl" in names,
        "trades": has_trades,
        "metrics": "metrics.json" in names,
        "ohlcv": has_ohlcv,
        "timeline": find_timeline_path(run_dir) is not None,
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
        artifacts_present = entry.get("artifacts_present")
        if not isinstance(artifacts_present, list):
            artifacts_present = []
        artifacts = _artifact_flags_from_present(run_dir, artifacts_present)
        listings.append(
            {
                "id": run_id,
                "run_id": run_id,
                "path": str(run_dir),
                "created_at": created_at,
                "status": status,
                "strategy": strategy,
                "symbols": [symbol] if symbol else None,
                "timeframe": timeframe,
                "has_trades": artifacts.get("trades", False),
                "artifacts": artifacts,
            }
        )
    return listings


def _invalid_run_id_response(run_id: str) -> JSONResponse:
    return error_response(400, "invalid_run_id", "Invalid run id", {"run_id": run_id})


def _resolve_registry_run_dir(
    runs_root: Path, run_id: str
) -> tuple[dict[str, object], Path] | JSONResponse:
    if _is_invalid_component(run_id):
        return _invalid_run_id_response(run_id)
    registry_result = _load_registry_with_lock(runs_root)
    if isinstance(registry_result, JSONResponse):
        return registry_result
    entry = _find_registry_entry(registry_result, run_id)
    if entry is None:
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    run_dir = (runs_root / run_id).resolve()
    if not is_within_root(run_dir, runs_root) or not run_dir.exists():
        return error_response(404, "RUN_NOT_FOUND", "Run not found", {"run_id": run_id})
    return entry, run_dir


def _resolve_run_dir_for_read(run_id: str) -> tuple[Path, str] | JSONResponse:
    readiness = _runs_root_readiness()
    if isinstance(readiness, JSONResponse):
        if _demo_mode_enabled():
            run_path = resolve_run_dir(run_id, get_artifacts_root())
            return run_path, "demo"
        return readiness
    runs_root, _ = readiness
    resolved = _resolve_registry_run_dir(runs_root, run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    _, run_dir = resolved
    return run_dir, "runs_root"


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "api_version": "1"}


@router.get("/ready", response_model=None)
def ready() -> object:
    readiness = _runs_root_readiness()
    if isinstance(readiness, JSONResponse):
        return readiness
    runs_root, runs_check = readiness
    registry_result = _load_registry_with_lock(runs_root)
    if isinstance(registry_result, JSONResponse):
        return registry_result
    runs = registry_result.get("runs") if isinstance(registry_result, dict) else []
    checks = {
        "runs_root": runs_check,
        "registry": {"status": "ok", "runs": len(runs) if isinstance(runs, list) else 0},
    }
    return {"status": "ready", "api_version": "1", "checks": checks}


@router.get("/runs")
def list_runs() -> object:
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
        return _mark_demo_runs(runs)

    runs_root, _ = readiness
    registry_result = _load_registry_with_lock(runs_root)
    if isinstance(registry_result, JSONResponse):
        return registry_result
    runs = registry_result.get("runs", []) if isinstance(registry_result, dict) else []
    return _build_registry_run_list(runs_root, runs if isinstance(runs, list) else [])


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


def _store_uploaded_csv(upload_bytes: bytes, runs_root: Path) -> str:
    repo_root = Path.cwd().resolve()
    if not is_within_root(runs_root, repo_root):
        raise RunBuilderError(
            "RUN_CONFIG_INVALID",
            "RUNS_ROOT must be within repo for uploads",
            400,
            {"runs_root": str(runs_root)},
        )

    uploads_dir = runs_root / "inputs"
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


@router.post("/runs")
async def create_run_endpoint(request: Request) -> JSONResponse:
    if _kill_switch_enabled():
        return error_response(
            503,
            "KILL_SWITCH_ENABLED",
            "Run creation disabled",
            {"env": KILL_SWITCH_ENV},
        )
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
        runs_root, _ = readiness
        try:
            upload_path = _store_uploaded_csv(bytes(file_part["data"]), runs_root)
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

    try:
        status_code, response = create_run(payload)
        return JSONResponse(status_code=status_code, content=response)
    except RunBuilderError as exc:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)
    except Exception:
        return error_response(500, "INTERNAL", "Internal error")


@router.get("/runs/{run_id}/manifest")
def run_manifest(run_id: str) -> JSONResponse:
    runs_root = get_runs_root()
    if runs_root is None:
        return error_response(404, "RUN_NOT_FOUND", "Run not found")
    invalid = _is_invalid_component(run_id)
    if invalid:
        return error_response(400, "RUN_CONFIG_INVALID", "Invalid run_id", {"run_id": run_id})

    registry_result = _load_registry_with_lock(runs_root)
    if isinstance(registry_result, JSONResponse):
        return registry_result
    entry = _find_registry_entry(registry_result, run_id)
    if entry is None:
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
def run_artifact(run_id: str, name: str):
    runs_root = get_runs_root()
    if runs_root is None:
        return error_response(404, "RUN_NOT_FOUND", "Run not found")
    if _is_invalid_component(run_id):
        return error_response(400, "RUN_CONFIG_INVALID", "Invalid run_id", {"run_id": run_id})
    if _is_invalid_component(name):
        return error_response(400, "RUN_CONFIG_INVALID", "Invalid artifact name", {"name": name})

    registry_result = _load_registry_with_lock(runs_root)
    if isinstance(registry_result, JSONResponse):
        return registry_result
    entry = _find_registry_entry(registry_result, run_id)
    if entry is None:
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
def run_summary(run_id: str) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode = resolved
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
    if mode == "demo":
        summary["mode"] = "demo"
    return summary


@router.get("/runs/{run_id}/decisions")
def decisions(
    run_id: str,
    symbol: list[str] | None = Query(default=None),
    action: list[str] | None = Query(default=None),
    severity: list[str] | None = Query(default=None),
    reason_code: list[str] | None = Query(default=None),
    start_ts: str | None = None,
    end_ts: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode = resolved
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
    start_ts: str | None = None,
    end_ts: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode = resolved
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
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode = resolved
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
    symbol: str | None = None,
    timeframe: str | None = None,
    start_ts: str | None = None,
    end_ts: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=10000),
) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode = resolved
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
def metrics(run_id: str) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode = resolved
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
def timeline(run_id: str, source: str = "auto") -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode = resolved
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
def errors(run_id: str) -> dict[str, object]:
    resolved = _resolve_run_dir_for_read(run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, mode = resolved
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
    format: str = "json",
    symbol: list[str] | None = Query(default=None),
    action: list[str] | None = Query(default=None),
    severity: list[str] | None = Query(default=None),
    reason_code: list[str] | None = Query(default=None),
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> StreamingResponse:
    resolved = _resolve_run_dir_for_read(run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, _ = resolved
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
def export_errors(run_id: str, format: str = "json") -> StreamingResponse:
    resolved = _resolve_run_dir_for_read(run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, _ = resolved
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
    format: str = "json",
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> StreamingResponse:
    resolved = _resolve_run_dir_for_read(run_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    run_path, _ = resolved
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


def _load_registry_with_lock(runs_root: Path) -> dict[str, object] | JSONResponse:
    lock = lock_registry(runs_root)
    try:
        with lock:
            return reconcile_registry(runs_root)
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
    if not candidate or candidate in {".", ".."}:
        return True
    if "/" in candidate or "\\" in candidate:
        return True
    if candidate.startswith("."):
        return True
    return False


def _artifact_media_type(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".jsonl") or lowered.endswith(".ndjson"):
        return "application/x-ndjson; charset=utf-8"
    if lowered.endswith(".json"):
        return "application/json; charset=utf-8"
    return "text/plain; charset=utf-8"
