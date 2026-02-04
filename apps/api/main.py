from __future__ import annotations

from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .artifacts import (
    build_summary,
    collect_error_records,
    discover_runs,
    filter_decisions,
    get_run_path,
    load_trades,
    parse_timestamp,
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
    run_path = get_run_path(run_id)
    if run_path is None:
        raise HTTPException(status_code=404, detail="Run not found")
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
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    run_path = get_run_path(run_id)
    if run_path is None:
        raise HTTPException(status_code=404, detail="Run not found")
    decision_path = run_path / "decision_records.jsonl"
    if not decision_path.exists():
        raise HTTPException(status_code=404, detail="decision_records.jsonl missing")
    if page < 1 or page_size < 1:
        raise HTTPException(status_code=400, detail="page and page_size must be >= 1")

    start_dt = _parse_query_timestamp(start_ts)
    end_dt = _parse_query_timestamp(end_ts)

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
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    run_path = get_run_path(run_id)
    if run_path is None:
        raise HTTPException(status_code=404, detail="Run not found")
    trade_path = run_path / "trades.parquet"
    if not trade_path.exists():
        raise HTTPException(status_code=404, detail="trades.parquet missing")
    if page < 1 or page_size < 1:
        raise HTTPException(status_code=400, detail="page and page_size must be >= 1")

    start_dt = _parse_query_timestamp(start_ts)
    end_dt = _parse_query_timestamp(end_ts)

    try:
        return load_trades(trade_path, start_dt, end_dt, page, page_size)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}/errors")
def errors(run_id: str) -> dict[str, object]:
    run_path = get_run_path(run_id)
    if run_path is None:
        raise HTTPException(status_code=404, detail="Run not found")
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
