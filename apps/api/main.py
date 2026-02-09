from __future__ import annotations

from datetime import datetime
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
    load_timeline,
    load_trade_markers,
    load_trades,
    resolve_ohlcv_path,
    resolve_run_dir,
    stream_decisions_export,
    stream_errors_export,
    stream_trades_export,
    validate_decision_records,
)
from .chat import router as chat_router
from .errors import build_error_payload, raise_api_error
from .plugins import list_active_plugins, list_failed_plugins
from .timeutils import coerce_ts_param

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "api_version": "1"}


@router.get("/runs")
def list_runs() -> list[dict[str, object]]:
    artifacts_root = get_artifacts_root()
    if not artifacts_root.exists():
        raise_api_error(
            404,
            "artifacts_root_missing",
            "Artifacts root not found",
            {"path": str(artifacts_root)},
        )
    return discover_runs()


@router.get("/plugins/active")
def list_active() -> dict[str, list[dict[str, object]]]:
    return list_active_plugins(get_artifacts_root())


@router.get("/plugins/failed")
def list_failed() -> dict[str, list[dict[str, object]]]:
    return list_failed_plugins(get_artifacts_root())


@router.get("/runs/{run_id}/summary")
def run_summary(run_id: str) -> dict[str, object]:
    run_path = resolve_run_dir(run_id, get_artifacts_root())
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
    run_path = resolve_run_dir(run_id, get_artifacts_root())
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

    return filter_decisions(
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


@router.get("/runs/{run_id}/trades")
def trades(
    run_id: str,
    start_ts: str | None = None,
    end_ts: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    run_path = resolve_run_dir(run_id, get_artifacts_root())
    trade_path = run_path / "trades.parquet"
    if not trade_path.exists():
        raise_api_error(404, "trades_missing", "trades.parquet missing", {"run_id": run_id})

    start_dt, end_dt = _parse_time_range(start_ts, end_ts)

    try:
        return load_trades(trade_path, start_dt, end_dt, page, page_size)
    except RuntimeError as exc:
        raise_api_error(422, "trades_invalid", str(exc), {"run_id": run_id})


@router.get("/runs/{run_id}/trades/markers")
def trade_markers(
    run_id: str,
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> dict[str, object]:
    run_path = resolve_run_dir(run_id, get_artifacts_root())
    trade_path = run_path / "trades.parquet"
    if not trade_path.exists():
        raise_api_error(404, "trades_missing", "trades.parquet missing", {"run_id": run_id})

    start_dt, end_dt = _parse_time_range(start_ts, end_ts)
    try:
        payload = load_trade_markers(trade_path, start_ts=start_dt, end_ts=end_dt)
    except RuntimeError as exc:
        raise_api_error(422, "trades_invalid", str(exc), {"run_id": run_id})
    payload["run_id"] = run_id
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
    run_path = resolve_run_dir(run_id, get_artifacts_root())
    ohlcv_path = resolve_ohlcv_path(run_path, timeframe)
    if ohlcv_path is None:
        raise_api_error(
            404,
            "ohlcv_missing",
            "OHLCV artifact missing",
            {"run_id": run_id, "timeframe": timeframe},
        )

    start_dt, end_dt = _parse_time_range(start_ts, end_ts)
    try:
        payload = load_ohlcv(ohlcv_path, start_ts=start_dt, end_ts=end_dt, limit=limit)
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
    payload["source"] = ohlcv_path.name
    return payload


@router.get("/runs/{run_id}/metrics")
def metrics(run_id: str) -> dict[str, object]:
    run_path = resolve_run_dir(run_id, get_artifacts_root())
    metrics_path = run_path / "metrics.json"
    if not metrics_path.exists():
        raise_api_error(404, "metrics_missing", "metrics.json missing", {"run_id": run_id})
    try:
        payload = load_metrics(metrics_path)
    except RuntimeError as exc:
        raise_api_error(422, "metrics_invalid", str(exc), {"run_id": run_id})
    payload.setdefault("run_id", run_id)
    return payload


@router.get("/runs/{run_id}/timeline")
def timeline(run_id: str, source: str = "auto") -> dict[str, object]:
    run_path = resolve_run_dir(run_id, get_artifacts_root())
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

    return {"run_id": run_id, "total": len(events), "events": events}


@router.get("/runs/{run_id}/errors")
def errors(run_id: str) -> dict[str, object]:
    run_path = resolve_run_dir(run_id, get_artifacts_root())
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
    return collect_error_records(decision_path)


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
    run_path = resolve_run_dir(run_id, get_artifacts_root())
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
    run_path = resolve_run_dir(run_id, get_artifacts_root())
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
    run_path = resolve_run_dir(run_id, get_artifacts_root())
    trade_path = run_path / "trades.parquet"
    if not trade_path.exists():
        raise_api_error(404, "trades_missing", "trades.parquet missing", {"run_id": run_id})

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
