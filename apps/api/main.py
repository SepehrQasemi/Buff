from __future__ import annotations

from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .artifacts import (
    build_summary,
    collect_error_records,
    discover_runs,
    filter_decisions,
    get_artifacts_root,
    load_trades,
    parse_timestamp,
    resolve_run_dir,
)

app = FastAPI(title="Buff Artifacts API", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/runs")
def list_runs() -> list[dict[str, object]]:
    return discover_runs()


@app.get("/api/runs/{run_id}/summary")
def run_summary(run_id: str) -> dict[str, object]:
    run_path = resolve_run_dir(run_id, get_artifacts_root())
    decision_path = run_path / "decision_records.jsonl"
    if not decision_path.exists():
        raise HTTPException(status_code=404, detail="decision_records.jsonl missing")
    return build_summary(decision_path)


@app.get("/api/runs/{run_id}/decisions")
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


@app.get("/api/runs/{run_id}/trades")
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


@app.get("/api/runs/{run_id}/errors")
def errors(run_id: str) -> dict[str, object]:
    run_path = resolve_run_dir(run_id, get_artifacts_root())
    decision_path = run_path / "decision_records.jsonl"
    if not decision_path.exists():
        raise HTTPException(status_code=404, detail="decision_records.jsonl missing")
    records = collect_error_records(decision_path)
    return {"total": len(records), "results": records}


def _parse_query_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = parse_timestamp(value)
    if parsed is None:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp: {value}")
    return parsed


def _parse_time_range(
    start_ts: str | None, end_ts: str | None
) -> tuple[datetime | None, datetime | None]:
    start_dt = _parse_query_timestamp(start_ts)
    end_dt = _parse_query_timestamp(end_ts)
    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(status_code=400, detail="start_ts must be <= end_ts")
    return start_dt, end_dt
