from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException

ARTIFACTS_ENV = "ARTIFACTS_ROOT"


def get_artifacts_root() -> Path:
    root = os.environ.get(ARTIFACTS_ENV, "./artifacts")
    return Path(root).expanduser().resolve()


def resolve_run_dir(run_id: str, artifacts_root: Path) -> Path:
    candidate_id = (run_id or "").strip()
    if (
        not candidate_id
        or candidate_id.startswith(".")
        or "/" in candidate_id
        or "\\" in candidate_id
        or ".." in candidate_id
    ):
        raise HTTPException(status_code=400, detail="run_id must be a simple folder name")

    root = artifacts_root.resolve()
    candidate = (root / candidate_id).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="run_id must stay within ARTIFACTS_ROOT"
        ) from exc
    if not candidate.exists() or not candidate.is_dir():
        raise HTTPException(status_code=404, detail="Run not found")
    return candidate


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = _parse_epoch(float(value))
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            dt = _parse_epoch(float(raw))
        else:
            if raw.endswith("Z"):
                raw = f"{raw[:-1]}+00:00"
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError:
                return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_timestamp(value: Any) -> str | None:
    dt = parse_timestamp(value)
    if dt is None:
        return None
    return dt.isoformat()


def _parse_epoch(value: float) -> datetime:
    seconds = value / 1000.0 if value > 1e11 else value
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


class DecisionRecords:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.malformed_lines = 0

    def __iter__(self) -> Iterable[dict[str, Any]]:
        self.malformed_lines = 0
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    self.malformed_lines += 1
                    continue
                if isinstance(payload, dict):
                    yield payload


def discover_runs() -> list[dict[str, Any]]:
    root = get_artifacts_root()
    if not root.exists():
        return []

    runs: list[dict[str, Any]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        run_id = child.name
        decision_path = child / "decision_records.jsonl"
        status = "OK" if decision_path.exists() else "INVALID"
        created_at_dt = _get_created_at(child, decision_path)
        created_at = created_at_dt.isoformat() if created_at_dt else None
        strategy = None
        symbols = None
        timeframe = None
        if decision_path.exists():
            strategy, symbols, timeframe = extract_run_metadata(decision_path)
        has_trades = (child / "trades.parquet").exists()
        runs.append(
            {
                "id": run_id,
                "path": str(child),
                "created_at": created_at,
                "status": status,
                "strategy": strategy,
                "symbols": symbols,
                "timeframe": timeframe,
                "has_trades": has_trades,
                "_sort": created_at_dt or datetime.min.replace(tzinfo=timezone.utc),
            }
        )

    runs.sort(key=lambda item: item["_sort"], reverse=True)
    for run in runs:
        run.pop("_sort", None)
    return runs


def extract_run_metadata(decision_path: Path) -> tuple[str | None, list[str] | None, str | None]:
    strategy = None
    symbols = None
    timeframe = None
    for record in DecisionRecords(decision_path):
        if strategy is None:
            strategy = _first_value(record, ["strategy", "strategy_id", "strategy_name"])
        if symbols is None:
            symbols = _extract_symbols(record)
        if timeframe is None:
            timeframe = _first_value(record, ["timeframe", "tf", "bar_size"])
        if strategy or symbols or timeframe:
            if strategy is not None and symbols is not None and timeframe is not None:
                break
    return strategy, symbols, timeframe


def build_summary(decision_path: Path) -> dict[str, Any]:
    records = DecisionRecords(decision_path)
    min_ts: datetime | None = None
    max_ts: datetime | None = None
    counts_by_action: dict[str, int] = {}
    counts_by_severity: dict[str, int] = {}

    for record in records:
        action = record.get("action")
        if action:
            action_key = str(action)
            counts_by_action[action_key] = counts_by_action.get(action_key, 0) + 1
        severity = record.get("severity") or record.get("risk_state")
        if severity:
            severity_key = str(severity)
            counts_by_severity[severity_key] = counts_by_severity.get(severity_key, 0) + 1
        ts = parse_timestamp(record.get("timestamp"))
        if ts is not None:
            min_ts = ts if min_ts is None or ts < min_ts else min_ts
            max_ts = ts if max_ts is None or ts > max_ts else max_ts

    return {
        "min_timestamp": min_ts.isoformat() if min_ts else None,
        "max_timestamp": max_ts.isoformat() if max_ts else None,
        "counts_by_action": counts_by_action,
        "counts_by_severity": counts_by_severity,
        "malformed_lines_count": records.malformed_lines,
    }


def filter_decisions(
    decision_path: Path,
    symbols: list[str] | None,
    actions: list[str] | None,
    severities: list[str] | None,
    reason_codes: list[str] | None,
    start_ts: datetime | None,
    end_ts: datetime | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    symbol_filter = _normalize_filter(symbols)
    action_filter = _normalize_filter(actions)
    severity_filter = _normalize_filter(severities)
    reason_filter = _normalize_filter(reason_codes)

    records = DecisionRecords(decision_path)
    results: list[dict[str, Any]] = []
    total = 0
    offset = (page - 1) * page_size

    for record in records:
        if not _matches_filters(
            record,
            symbol_filter,
            action_filter,
            severity_filter,
            reason_filter,
            start_ts,
            end_ts,
        ):
            continue
        total += 1
        if total <= offset:
            continue
        if len(results) >= page_size:
            continue
        results.append(_normalize_record(record))

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": results,
    }


def collect_error_records(decision_path: Path) -> list[dict[str, Any]]:
    records = DecisionRecords(decision_path)
    results: list[dict[str, Any]] = []
    for record in records:
        if _is_error_record(record):
            results.append(_normalize_record(record))
    return results


def load_trades(
    trade_path: Path,
    start_ts: datetime | None,
    end_ts: datetime | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - env issue
        raise RuntimeError("pandas is required to read trades.parquet") from exc

    df = pd.read_parquet(trade_path)
    if df.empty:
        return {"total": 0, "page": page, "page_size": page_size, "results": []}

    timestamp_col = _pick_timestamp_column(df.columns)
    if timestamp_col:
        ts = pd.to_datetime(df[timestamp_col], utc=True, errors="coerce")
        mask = ts.notna()
        if start_ts is not None:
            mask &= ts >= start_ts
        if end_ts is not None:
            mask &= ts <= end_ts
        df = df[mask].copy()
        ts = ts[mask]
        df[timestamp_col] = ts

    total = len(df)
    start = (page - 1) * page_size
    end = start + page_size
    page_df = df.iloc[start:end]
    records = page_df.to_dict(orient="records")
    if timestamp_col:
        for record in records:
            normalized = normalize_timestamp(record.get(timestamp_col))
            if normalized is not None:
                record[timestamp_col] = normalized

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": records,
        "timestamp_field": timestamp_col,
    }


def _get_created_at(run_path: Path, decision_path: Path) -> datetime | None:
    target = decision_path if decision_path.exists() else run_path
    try:
        ts = target.stat().st_mtime
    except FileNotFoundError:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _metadata(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _first_value(record: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = record.get(key)
        if value is not None:
            return str(value)
    metadata = _metadata(record)
    for key in keys:
        value = metadata.get(key)
        if value is not None:
            return str(value)
    return None


def _extract_symbols(record: dict[str, Any]) -> list[str] | None:
    value = record.get("symbols")
    if value is None:
        value = record.get("symbol")
    if value is None:
        metadata = _metadata(record)
        value = metadata.get("symbols") or metadata.get("symbol")
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _normalize_filter(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    return {str(value) for value in values if value is not None}


def _matches_filters(
    record: dict[str, Any],
    symbol_filter: set[str] | None,
    action_filter: set[str] | None,
    severity_filter: set[str] | None,
    reason_filter: set[str] | None,
    start_ts: datetime | None,
    end_ts: datetime | None,
) -> bool:
    if symbol_filter:
        symbols = _extract_symbols(record)
        if not symbols or not symbol_filter.intersection(symbols):
            return False

    if action_filter and not _matches_value(record.get("action"), action_filter):
        return False

    severity_value = record.get("severity") or record.get("risk_state")
    if severity_filter and not _matches_value(severity_value, severity_filter):
        return False

    reason_value = record.get("reason_code") or record.get("reason")
    if reason_filter and not _matches_value(reason_value, reason_filter):
        return False

    if start_ts or end_ts:
        ts = parse_timestamp(record.get("timestamp"))
        if ts is None:
            return False
        if start_ts and ts < start_ts:
            return False
        if end_ts and ts > end_ts:
            return False

    return True


def _matches_value(value: Any, allowed: set[str]) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return any(str(item) in allowed for item in value if item is not None)
    return str(value) in allowed


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    if "timestamp" in normalized:
        normalized_ts = normalize_timestamp(normalized.get("timestamp"))
        if normalized_ts is not None:
            normalized["timestamp"] = normalized_ts
    return normalized


def _is_error_record(record: dict[str, Any]) -> bool:
    severity = record.get("severity") or record.get("risk_state") or ""
    severity_key = str(severity).upper()
    if severity_key in {"ERROR", "FAIL_CLOSED", "FAIL-CLOSED", "FAILCLOSED"}:
        return True
    return False


def _pick_timestamp_column(columns: Iterable[str]) -> str | None:
    for name in ("timestamp", "time", "ts", "date"):
        if name in columns:
            return name
    return None
