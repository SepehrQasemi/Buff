from __future__ import annotations

import csv
import io
import json
import os
from collections import OrderedDict, deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Iterable

from .errors import raise_api_error
from .timeutils import format_ts, parse_ts

_CACHE_MAX_ENTRIES = 32
_ERRORS_LIMIT = 2000
_MALFORMED_SAMPLE_LIMIT = 5
_OHLCV_REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}
_TIMESTAMP_FIELDS = ("timestamp", "timestamp_utc", "ts_utc", "ts", "time", "date")


class _LRUCache:
    def __init__(self, max_entries: int) -> None:
        self._max_entries = max_entries
        self._lock = Lock()
        self._data: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()

    def get(self, key: tuple[Any, ...]) -> dict[str, Any] | None:
        with self._lock:
            value = self._data.get(key)
            if value is None:
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: tuple[Any, ...], value: dict[str, Any]) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False)


_DECISION_CACHE = _LRUCache(_CACHE_MAX_ENTRIES)

ARTIFACTS_ENV = "ARTIFACTS_ROOT"
_TIMELINE_FILENAMES = (
    "timeline.json",
    "timeline_events.json",
    "risk_timeline.json",
    "selector_trace.json",
)


def get_artifacts_root() -> Path:
    root = os.environ.get(ARTIFACTS_ENV, "./artifacts")
    return Path(root).expanduser().resolve()


def resolve_run_dir(run_id: str, artifacts_root: Path) -> Path:
    candidate_id = (run_id or "").strip()
    if (
        not candidate_id
        or candidate_id in {".", ".."}
        or candidate_id.startswith(".")
        or "/" in candidate_id
        or "\\" in candidate_id
    ):
        raise_api_error(
            400,
            "invalid_run_id",
            "Invalid run id",
            {"run_id": run_id},
        )

    root = artifacts_root.resolve()
    candidate = (root / candidate_id).resolve()
    if not _is_within_root(candidate, root):
        raise_api_error(
            400,
            "invalid_run_id",
            "Invalid run id",
            {"run_id": run_id},
        )
    if not candidate.exists() or not candidate.is_dir():
        raise_api_error(
            404,
            "run_not_found",
            "Run not found",
            {"run_id": run_id},
        )
    return candidate


def collect_run_artifacts(run_path: Path) -> dict[str, bool]:
    return {
        "decisions": (run_path / "decision_records.jsonl").exists(),
        "trades": (run_path / "trades.parquet").exists(),
        "metrics": (run_path / "metrics.json").exists(),
        "ohlcv": _has_ohlcv_artifact(run_path),
        "timeline": find_timeline_path(run_path) is not None,
        "risk_report": (run_path / "risk_report.json").exists(),
        "manifest": (run_path / "run_manifest.json").exists(),
    }


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
        created_at = format_ts(created_at_dt)
        strategy = None
        symbols = None
        timeframe = None
        if decision_path.exists():
            strategy, symbols, timeframe = extract_run_metadata(decision_path)
        artifacts = collect_run_artifacts(child)
        has_trades = artifacts["trades"]
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
                "artifacts": artifacts,
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
    summary, _ = _get_cached_analysis(decision_path)
    return summary


def validate_decision_records(decision_path: Path) -> dict[str, Any]:
    summary, _ = _get_cached_analysis(decision_path)
    malformed = int(summary.get("malformed_lines_count") or 0)
    if malformed == 0:
        return {}
    return {
        "malformed_lines_count": malformed,
        "malformed_samples": summary.get("malformed_samples") or [],
        "malformed_samples_detail": summary.get("malformed_samples_detail") or [],
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
        "items": results,
    }


def collect_error_records(decision_path: Path) -> dict[str, Any]:
    _, errors = _get_cached_analysis(decision_path)
    return errors


def stream_decisions_export(
    decision_path: Path,
    *,
    symbols: list[str] | None,
    actions: list[str] | None,
    severities: list[str] | None,
    reason_codes: list[str] | None,
    start_ts: datetime | None,
    end_ts: datetime | None,
    fmt: str,
) -> tuple[Iterable[bytes], str]:
    def iter_records() -> Iterable[dict[str, Any]]:
        yield from _iter_filtered_decisions(
            decision_path,
            symbols,
            actions,
            severities,
            reason_codes,
            start_ts,
            end_ts,
        )

    return _build_export_stream(iter_records, fmt)


def stream_errors_export(decision_path: Path, *, fmt: str) -> tuple[Iterable[bytes], str]:
    def iter_records() -> Iterable[dict[str, Any]]:
        yield from _iter_error_records(decision_path)

    return _build_export_stream(iter_records, fmt)


def stream_trades_export(
    trade_path: Path, *, start_ts: datetime | None, end_ts: datetime | None, fmt: str
) -> tuple[Iterable[bytes], str]:
    def iter_records() -> Iterable[dict[str, Any]]:
        yield from _iter_trade_records(trade_path, start_ts, end_ts)

    return _build_export_stream(iter_records, fmt)


def _get_cached_analysis(decision_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    cache_key = _decision_cache_key(decision_path)
    cached = _DECISION_CACHE.get(cache_key)
    if cached is not None:
        return cached["summary"], cached["errors"]

    summary, errors = _scan_decision_records(decision_path)
    _DECISION_CACHE.set(cache_key, {"summary": summary, "errors": errors})
    return summary, errors


def _decision_cache_key(decision_path: Path) -> tuple[Any, ...]:
    stat = decision_path.stat()
    run_id = decision_path.parent.name
    return (run_id, stat.st_mtime_ns, stat.st_size)


def _scan_decision_records(decision_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    min_ts: datetime | None = None
    max_ts: datetime | None = None
    counts_by_action: dict[str, int] = {}
    counts_by_severity: dict[str, int] = {}
    malformed_lines_count = 0
    malformed_samples: list[str] = []
    malformed_samples_detail: list[dict[str, Any]] = []
    total_errors = 0
    errors = deque(maxlen=_ERRORS_LIMIT)
    provenance: dict[str, Any] = {
        "strategy_id": None,
        "strategy_version": None,
        "data_snapshot_hash": None,
        "feature_snapshot_hash": None,
    }
    risk_summary: dict[str, Any] = {
        "level": None,
        "state": None,
        "permission": None,
        "blocked": None,
        "reason": None,
        "rule_id": None,
        "policy_type": None,
        "status": "missing",
    }
    latest_risk_ts: datetime | None = None

    with decision_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                malformed_lines_count += 1
                if len(malformed_samples) < _MALFORMED_SAMPLE_LIMIT:
                    malformed_samples.append(line)
                if len(malformed_samples_detail) < _MALFORMED_SAMPLE_LIMIT:
                    malformed_samples_detail.append(
                        {
                            "line_number": line_number,
                            "error": str(exc),
                            "raw_preview": _truncate_preview(line),
                        }
                    )
                continue
            if not isinstance(payload, dict):
                continue

            action = payload.get("action")
            if action:
                action_key = str(action)
                counts_by_action[action_key] = counts_by_action.get(action_key, 0) + 1
            severity = payload.get("severity") or payload.get("risk_state")
            if severity:
                severity_key = str(severity)
                counts_by_severity[severity_key] = counts_by_severity.get(severity_key, 0) + 1

            try:
                ts = parse_ts(_record_timestamp(payload))
            except ValueError:
                ts = None
            if ts is not None:
                min_ts = ts if min_ts is None or ts < min_ts else min_ts
                max_ts = ts if max_ts is None or ts > max_ts else max_ts

            if _is_error_record(payload):
                total_errors += 1
                errors.append(_normalize_record(payload))

            _update_provenance(provenance, payload)
            _update_risk_summary(risk_summary, payload, ts, latest_risk_ts)
            if risk_summary.get("status") == "ok" and ts is not None:
                if latest_risk_ts is None or ts > latest_risk_ts:
                    latest_risk_ts = ts

    summary = {
        "min_timestamp": format_ts(min_ts),
        "max_timestamp": format_ts(max_ts),
        "counts_by_action": counts_by_action,
        "counts_by_severity": counts_by_severity,
        "malformed_lines_count": malformed_lines_count,
        "malformed_samples": malformed_samples,
        "malformed_samples_detail": malformed_samples_detail,
        "provenance": provenance,
        "risk": risk_summary,
    }
    error_list = list(errors)
    errors_payload = {
        "total_errors": total_errors,
        "returned_errors_count": len(error_list),
        "errors": error_list,
        "total": total_errors,
        "results": error_list,
    }
    return summary, errors_payload


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
            normalized = _format_timestamp_value(record.get(timestamp_col))
            if normalized is not None:
                record[timestamp_col] = normalized
            else:
                record[timestamp_col] = None

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": records,
        "timestamp_field": timestamp_col,
    }


def load_trade_markers(
    trade_path: Path, *, start_ts: datetime | None, end_ts: datetime | None
) -> dict[str, Any]:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - env issue
        raise RuntimeError("pandas is required to read trades.parquet") from exc

    df = pd.read_parquet(trade_path)
    if df.empty:
        return {"total": 0, "markers": []}

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

    if df.empty:
        return {"total": 0, "markers": []}

    price_col = _pick_price_column(df.columns)
    markers: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        timestamp = _format_timestamp_value(row[timestamp_col]) if timestamp_col else None
        if timestamp is None:
            continue
        side = row.get("side") or row.get("direction") or row.get("action")
        side_str = str(side).upper() if side is not None else ""
        marker_type = "event"
        if side_str in {"BUY", "LONG", "ENTER_LONG", "ENTRY"}:
            marker_type = "entry"
        elif side_str in {"SELL", "SHORT", "EXIT_LONG", "EXIT_SHORT", "EXIT"}:
            marker_type = "exit"

        price = None
        if price_col:
            try:
                price = float(row[price_col])
            except (TypeError, ValueError):
                price = None

        marker = {
            "timestamp": timestamp,
            "price": price,
            "side": side_str or None,
            "marker_type": marker_type,
            "pnl": row.get("pnl"),
            "trade_id": row.get("trade_id") or row.get("id"),
        }
        markers.append(marker)

    return {"total": len(markers), "markers": markers}


def load_ohlcv(
    ohlcv_path: Path,
    *,
    start_ts: datetime | None,
    end_ts: datetime | None,
    limit: int | None,
) -> dict[str, Any]:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - env issue
        raise RuntimeError("pandas is required to read OHLCV parquet") from exc

    df = pd.read_parquet(ohlcv_path)
    if df.empty:
        return {"count": 0, "candles": []}

    ts_col = _pick_timestamp_column(df.columns)
    if ts_col is None:
        raise RuntimeError("ohlcv parquet missing timestamp column")

    missing_cols = _OHLCV_REQUIRED_COLUMNS - set(df.columns)
    if missing_cols:
        raise RuntimeError(f"ohlcv parquet missing columns: {','.join(sorted(missing_cols))}")

    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    mask = ts.notna()
    if start_ts is not None:
        mask &= ts >= start_ts
    if end_ts is not None:
        mask &= ts <= end_ts
    df = df[mask].copy()
    ts = ts[mask]
    df[ts_col] = ts

    if df.empty:
        return {"count": 0, "candles": []}

    df = df.sort_values(ts_col)
    if limit is not None and limit > 0:
        df = df.iloc[:limit]

    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        record = {
            "ts": _format_timestamp_value(row[ts_col]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        records.append(record)

    start_value = records[0]["ts"] if records else None
    end_value = records[-1]["ts"] if records else None
    return {"count": len(records), "start_ts": start_value, "end_ts": end_value, "candles": records}


def load_metrics(metrics_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - upstream check
        raise RuntimeError("metrics.json missing") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("metrics.json invalid") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("metrics.json must be an object")
    return payload


def load_timeline(timeline_path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(timeline_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - upstream check
        raise RuntimeError("timeline artifact missing") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("timeline artifact invalid") from exc
    if not isinstance(payload, list):
        raise RuntimeError("timeline artifact must be a list")
    return [item for item in payload if isinstance(item, dict)]


def build_timeline_from_decisions(
    decision_path: Path, *, limit: int = 1000
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for record in DecisionRecords(decision_path):
        ts = _record_timestamp(record)
        try:
            ts_dt = parse_ts(ts)
        except ValueError:
            ts_dt = None
        if ts_dt is None:
            continue

        event = {
            "timestamp": format_ts(ts_dt),
            "type": _timeline_type(record),
            "title": _timeline_title(record),
            "detail": _timeline_detail(record),
            "severity": _timeline_severity(record),
            "risk": _extract_risk_info(record),
        }
        events.append(event)
        if len(events) >= limit:
            break

    events.sort(key=lambda item: item.get("timestamp") or "")
    return events


def _iter_filtered_decisions(
    decision_path: Path,
    symbols: list[str] | None,
    actions: list[str] | None,
    severities: list[str] | None,
    reason_codes: list[str] | None,
    start_ts: datetime | None,
    end_ts: datetime | None,
) -> Iterable[dict[str, Any]]:
    symbol_filter = _normalize_filter(symbols)
    action_filter = _normalize_filter(actions)
    severity_filter = _normalize_filter(severities)
    reason_filter = _normalize_filter(reason_codes)

    for record in DecisionRecords(decision_path):
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
        yield _normalize_record(record)


def _iter_error_records(decision_path: Path) -> Iterable[dict[str, Any]]:
    for record in DecisionRecords(decision_path):
        if _is_error_record(record):
            yield _normalize_record(record)


def _iter_trade_records(
    trade_path: Path, start_ts: datetime | None, end_ts: datetime | None
) -> Iterable[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - env issue
        raise RuntimeError("pyarrow is required to read trades.parquet") from exc

    parquet = pq.ParquetFile(trade_path)
    timestamp_col = _pick_timestamp_column(parquet.schema.names)

    for batch in parquet.iter_batches():
        table = batch.to_pandas()
        records = table.to_dict(orient="records")
        for record in records:
            ts_value = record.get(timestamp_col) if timestamp_col else None
            ts = None
            if timestamp_col:
                try:
                    ts = parse_ts(ts_value)
                except ValueError:
                    ts = None
            if start_ts and (ts is None or ts < start_ts):
                continue
            if end_ts and (ts is None or ts > end_ts):
                continue
            if timestamp_col:
                record[timestamp_col] = format_ts(ts)
            yield record


def _build_export_stream(
    record_iter_factory: Callable[[], Iterable[dict[str, Any]]], fmt: str
) -> tuple[Iterable[bytes], str]:
    fmt_lower = fmt.lower()
    if fmt_lower == "json":
        return _stream_json_array(record_iter_factory), "application/json; charset=utf-8"
    if fmt_lower == "ndjson":
        return _stream_ndjson(record_iter_factory), "application/x-ndjson; charset=utf-8"
    if fmt_lower == "csv":
        return _stream_csv(record_iter_factory), "text/csv; charset=utf-8"
    raise ValueError(f"Unsupported export format: {fmt}")


def _stream_csv(record_iter_factory: Callable[[], Iterable[dict[str, Any]]]) -> Iterable[bytes]:
    record_iter = iter(record_iter_factory())
    try:
        first_record = next(record_iter)
    except StopIteration:
        return

    fieldnames = list(first_record.keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    yield output.getvalue().encode("utf-8")
    output.seek(0)
    output.truncate(0)

    writer.writerow(_sanitize_csv_row(first_record))
    yield output.getvalue().encode("utf-8")
    output.seek(0)
    output.truncate(0)

    for record in record_iter:
        writer.writerow(_sanitize_csv_row(record))
        yield output.getvalue().encode("utf-8")
        output.seek(0)
        output.truncate(0)


def _stream_json_array(
    record_iter_factory: Callable[[], Iterable[dict[str, Any]]],
) -> Iterable[bytes]:
    yield b"["
    first = True
    for record in record_iter_factory():
        if not first:
            yield b","
        yield json.dumps(record).encode("utf-8")
        first = False
    yield b"]"


def _stream_ndjson(record_iter_factory: Callable[[], Iterable[dict[str, Any]]]) -> Iterable[bytes]:
    for record in record_iter_factory():
        yield json.dumps(record).encode("utf-8") + b"\n"


def _sanitize_csv_row(record: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in record.items():
        sanitized[key] = _sanitize_csv_value(value)
    return sanitized


def _sanitize_csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        value = json.dumps(value)
    if not isinstance(value, str):
        return value
    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


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
        try:
            ts = parse_ts(_record_timestamp(record))
        except ValueError:
            ts = None
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
        normalized["timestamp"] = _format_timestamp_value(normalized.get("timestamp"))
    elif "timestamp_utc" in normalized:
        normalized["timestamp"] = _format_timestamp_value(normalized.get("timestamp_utc"))
    elif "ts_utc" in normalized:
        normalized["timestamp"] = _format_timestamp_value(normalized.get("ts_utc"))
    return normalized


def _is_error_record(record: dict[str, Any]) -> bool:
    severity = record.get("severity") or record.get("risk_state") or ""
    severity_key = str(severity).upper()
    if severity_key in {"ERROR", "FAIL_CLOSED", "FAIL-CLOSED", "FAILCLOSED"}:
        return True
    return False


def _pick_timestamp_column(columns: Iterable[str]) -> str | None:
    for name in _TIMESTAMP_FIELDS:
        if name in columns:
            return name
    return None


def _pick_price_column(columns: Iterable[str]) -> str | None:
    for name in ("price", "entry_price", "exit_price", "price_raw", "fill_price", "avg_price"):
        if name in columns:
            return name
    return None


def _has_ohlcv_artifact(run_path: Path) -> bool:
    if (run_path / "ohlcv.parquet").exists() or (run_path / "ohlcv_1m.parquet").exists():
        return True
    for candidate in run_path.glob("ohlcv_*.parquet"):
        if candidate.is_file():
            return True
    return False


def resolve_ohlcv_path(run_path: Path, timeframe: str | None) -> Path | None:
    candidates: list[Path] = []
    if timeframe:
        candidates.append(run_path / f"ohlcv_{timeframe}.parquet")
        if timeframe == "1m":
            candidates.append(run_path / "ohlcv_1m.parquet")
    candidates.append(run_path / "ohlcv.parquet")
    if not timeframe:
        candidates.append(run_path / "ohlcv_1m.parquet")
        candidates.extend(sorted(run_path.glob("ohlcv_*.parquet")))

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def find_timeline_path(run_path: Path) -> Path | None:
    for name in _TIMELINE_FILENAMES:
        path = run_path / name
        if path.exists() and path.is_file():
            return path
    return None


def _record_timestamp(record: dict[str, Any]) -> Any:
    for key in _TIMESTAMP_FIELDS:
        if key in record:
            return record.get(key)
    metadata = _metadata(record)
    for key in _TIMESTAMP_FIELDS:
        if key in metadata:
            return metadata.get(key)
    return None


def _update_provenance(target: dict[str, Any], record: dict[str, Any]) -> None:
    if target.get("strategy_id") is None:
        target["strategy_id"] = _first_value(
            record, ["strategy_id", "strategy", "strategy_name", "strategyId"]
        )
        selection = record.get("selection")
        if target.get("strategy_id") is None and isinstance(selection, dict):
            target["strategy_id"] = selection.get("strategy_id") or selection.get("strategyId")

    if target.get("strategy_version") is None:
        target["strategy_version"] = _first_value(
            record, ["strategy_version", "strategyVersion", "version"]
        )
        selection = record.get("selection")
        if target.get("strategy_version") is None and isinstance(selection, dict):
            target["strategy_version"] = selection.get("strategy_version") or selection.get(
                "strategyVersion"
            )
        strategy = record.get("strategy")
        if target.get("strategy_version") is None and isinstance(strategy, dict):
            target["strategy_version"] = strategy.get("version")

    if target.get("data_snapshot_hash") is None:
        target["data_snapshot_hash"] = _first_value(
            record, ["data_snapshot_hash", "dataSnapshotHash", "snapshot_hash", "snapshotHash"]
        )
        artifacts = record.get("artifacts")
        if target.get("data_snapshot_hash") is None and isinstance(artifacts, dict):
            target["data_snapshot_hash"] = artifacts.get("snapshot_ref") or artifacts.get(
                "snapshotRef"
            )

    if target.get("feature_snapshot_hash") is None:
        target["feature_snapshot_hash"] = _first_value(
            record,
            ["feature_snapshot_hash", "featureSnapshotHash", "features_hash", "featuresHash"],
        )
        artifacts = record.get("artifacts")
        if target.get("feature_snapshot_hash") is None and isinstance(artifacts, dict):
            target["feature_snapshot_hash"] = artifacts.get("features_ref") or artifacts.get(
                "featuresRef"
            )


def _extract_risk_info(record: dict[str, Any]) -> dict[str, Any]:
    risk = record.get("risk")
    risk_obj = risk if isinstance(risk, dict) else {}
    level = _first_value(record, ["risk_level", "riskLevel"])
    if level is None:
        level = risk_obj.get("level") or risk_obj.get("risk_level")
    state = _first_value(record, ["risk_state", "risk_status"])
    if state is None:
        state = risk_obj.get("state") or risk_obj.get("risk_state")
    permission = _first_value(record, ["permission", "risk_permission"])
    if permission is None:
        permission = risk_obj.get("permission")

    reason = _first_value(record, ["risk_reason", "reason", "reason_code", "risk_rule"])
    if reason is None:
        reasons = risk_obj.get("reasons")
        if isinstance(reasons, (list, tuple)):
            reason = ", ".join(str(item) for item in reasons if item is not None) or None
        elif isinstance(reasons, str):
            reason = reasons

    rule_id = _first_value(record, ["risk_rule_id", "rule_id", "risk_rule"])
    if rule_id is None:
        rule_id = risk_obj.get("rule_id") or risk_obj.get("rule")

    policy_raw = _first_value(record, ["risk_policy_type", "policy_type", "risk_layer"])
    if policy_raw is None:
        policy_raw = risk_obj.get("policy_type") or risk_obj.get("layer")
    policy_type = _normalize_policy_type(policy_raw)

    blocked = _infer_blocked(record, permission)

    return {
        "level": _coerce_int(level),
        "state": str(state) if state is not None else None,
        "permission": str(permission) if permission is not None else None,
        "blocked": blocked,
        "reason": str(reason) if reason is not None else None,
        "rule_id": str(rule_id) if rule_id is not None else None,
        "policy_type": policy_type,
    }


def _update_risk_summary(
    target: dict[str, Any], record: dict[str, Any], ts: datetime | None, latest_ts: datetime | None
) -> None:
    info = _extract_risk_info(record)
    has_info = any(value is not None for value in info.values())
    if not has_info:
        return
    if latest_ts is not None and ts is not None and ts < latest_ts:
        return
    target.update(info)
    target["status"] = "ok"


def _infer_blocked(record: dict[str, Any], permission: Any) -> bool | None:
    if permission is not None:
        permission_str = str(permission).upper()
        if permission_str in {"BLOCK", "BLOCKED", "DENY"}:
            return True
        if permission_str in {"ALLOW", "RESTRICT", "LIMIT"}:
            return False

    for key in ("execution_status", "action", "decision", "status"):
        value = record.get(key)
        if value is None:
            continue
        value_str = str(value).upper()
        if value_str in {"BLOCKED", "BLOCK", "DENIED", "FAIL_CLOSED", "FAIL-CLOSED"}:
            return True
        if value_str in {"EXECUTED", "ALLOWED", "ALLOW", "OK"}:
            return False
    return None


def _normalize_policy_type(value: Any) -> str | None:
    if value is None:
        return None
    value_str = str(value).lower()
    if "hard" in value_str or "cap" in value_str:
        return "hard_cap"
    if "user" in value_str or "policy" in value_str:
        return "user_policy"
    return "unknown"


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        num = int(value)
    except (TypeError, ValueError):
        return None
    return num if 1 <= num <= 5 else num


def _timeline_type(record: dict[str, Any]) -> str:
    action = str(record.get("action") or record.get("decision") or "").lower()
    if action in {"blocked", "block", "fail_closed", "fail-closed"}:
        return "risk"
    if _is_error_record(record):
        return "error"
    return "decision"


def _timeline_title(record: dict[str, Any]) -> str:
    for key in ("action", "decision", "execution_status", "selection"):
        value = record.get(key)
        if isinstance(value, dict):
            status = value.get("status")
            if status:
                return str(status)
        if value:
            return str(value)
    return "decision"


def _timeline_detail(record: dict[str, Any]) -> str | None:
    for key in ("reason", "reason_code", "message", "note"):
        value = record.get(key)
        if value:
            return str(value)
    risk = record.get("risk")
    if isinstance(risk, dict):
        reason = risk.get("reason") or risk.get("reasons")
        if isinstance(reason, (list, tuple)):
            return ", ".join(str(item) for item in reason if item is not None) or None
        if isinstance(reason, str):
            return reason
    return None


def _timeline_severity(record: dict[str, Any]) -> str:
    severity = record.get("severity") or record.get("risk_state")
    if severity is None:
        return "INFO"
    return str(severity).upper()


def _format_timestamp_value(value: Any) -> str | None:
    try:
        return format_ts(parse_ts(value))
    except ValueError:
        return None


def _truncate_preview(value: str, limit: int = 300) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."


def _is_within_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        return candidate == root or root in candidate.parents
