from __future__ import annotations

from datetime import datetime
from typing import Iterable
from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .artifacts import (
    build_summary,
    collect_error_records,
    discover_runs,
    filter_decisions,
    get_artifacts_root,
    load_trades,
    stream_decisions_export,
    stream_errors_export,
    stream_trades_export,
    resolve_run_dir,
)
from .timeutils import coerce_ts_param

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "api_version": "1"}


@router.get("/runs")
def list_runs() -> list[dict[str, object]]:
    return discover_runs()


@router.get("/runs/{run_id}/summary")
def run_summary(run_id: str) -> dict[str, object]:
    run_path = resolve_run_dir(run_id, get_artifacts_root())
    decision_path = run_path / "decision_records.jsonl"
    if not decision_path.exists():
        raise HTTPException(status_code=404, detail="decision_records.jsonl missing")
    return build_summary(decision_path)


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
        raise HTTPException(status_code=404, detail="decision_records.jsonl missing")

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
        raise HTTPException(status_code=404, detail="trades.parquet missing")

    start_dt, end_dt = _parse_time_range(start_ts, end_ts)

    try:
        return load_trades(trade_path, start_dt, end_dt, page, page_size)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runs/{run_id}/errors")
def errors(run_id: str) -> dict[str, object]:
    run_path = resolve_run_dir(run_id, get_artifacts_root())
    decision_path = run_path / "decision_records.jsonl"
    if not decision_path.exists():
        raise HTTPException(status_code=404, detail="decision_records.jsonl missing")
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
        raise HTTPException(status_code=404, detail="decision_records.jsonl missing")

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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _export_response(stream, media_type, f"{run_id}-decisions.{format}")


@router.get("/runs/{run_id}/errors/export")
def export_errors(run_id: str, format: str = "json") -> StreamingResponse:
    run_path = resolve_run_dir(run_id, get_artifacts_root())
    decision_path = run_path / "decision_records.jsonl"
    if not decision_path.exists():
        raise HTTPException(status_code=404, detail="decision_records.jsonl missing")

    try:
        stream, media_type = stream_errors_export(decision_path, fmt=format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        raise HTTPException(status_code=404, detail="trades.parquet missing")

    start_dt, end_dt = _parse_time_range(start_ts, end_ts)
    try:
        stream, media_type = stream_trades_export(
            trade_path, start_ts=start_dt, end_ts=end_dt, fmt=format
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


def _parse_time_range(
    start_ts: str | None, end_ts: str | None
) -> tuple[datetime | None, datetime | None]:
    start_dt = coerce_ts_param(start_ts, "start_ts")
    end_dt = coerce_ts_param(end_ts, "end_ts")
    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(status_code=400, detail="start_ts must be <= end_ts")
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
        raise HTTPException(status_code=400, detail=f"{name} supports at most 50 values")
    return normalized or None


def _export_response(stream: Iterable[bytes], media_type: str, filename: str) -> StreamingResponse:
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(stream, media_type=media_type, headers=headers)
