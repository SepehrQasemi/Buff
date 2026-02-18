from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from buff.data.resample import resample_ohlcv

from .canonical import to_canonical_bytes, write_canonical_json, write_canonical_jsonl
from .engine import EngineConfig, run_engine
from .numeric import NonFiniteNumberError
from .paths import (
    RUNS_ROOT_ENV,
    get_runs_root,
    is_within_root,
    run_dir as resolve_user_run_dir,
    user_root,
    user_runs_root,
    validate_user_id,
)
from .registry import compute_inputs_hash, lock_registry, upsert_registry_entry

ENGINE_VERSION = "phase6-1.0.0"
BUILDER_VERSION = "phase6-1.0.0"
INITIAL_EQUITY = 10_000.0

RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


@dataclass
class RunBuilderError(Exception):
    code: str
    message: str
    status_code: int
    details: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details or {},
        }


def create_run(
    payload: dict[str, Any], *, user_id: str | None = None
) -> tuple[int, dict[str, Any]]:
    if not isinstance(payload, dict):
        raise RunBuilderError("RUN_CONFIG_INVALID", "Request body must be an object", 400)

    owner_user_id = _resolve_owner_user_id(user_id)
    normalized, meta = _normalize_request(payload)
    inputs_hash = compute_inputs_hash(to_canonical_bytes(normalized))

    run_id = payload.get("run_id")
    if run_id is not None:
        run_id = str(run_id).strip()
        if not RUN_ID_PATTERN.match(run_id or ""):
            raise RunBuilderError("RUN_ID_INVALID", "run_id is invalid", 400, {"run_id": run_id})
    else:
        run_id = f"run_{inputs_hash[:12]}"

    base_runs_root = _resolve_runs_root()
    owner_root = user_root(base_runs_root, owner_user_id)
    runs_root = user_runs_root(base_runs_root, owner_user_id)
    runs_root.mkdir(parents=True, exist_ok=True)

    run_dir = resolve_user_run_dir(base_runs_root, owner_user_id, run_id).resolve()
    if not is_within_root(run_dir, runs_root):
        raise RunBuilderError("RUN_ID_INVALID", "run_id resolved outside runs root", 400)

    if run_dir.exists():
        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = None
        else:
            manifest = None

        if manifest and manifest.get("inputs_hash") == inputs_hash:
            _ensure_registry_entry(owner_root, run_dir, manifest)
            return 200, _success_response(
                run_id,
                manifest.get("status") or "COMPLETED",
                inputs_hash,
            )
        raise RunBuilderError("RUN_EXISTS", "run_id already exists", 409, {"run_id": run_id})

    df_1m, data_meta = _load_and_validate_csv(normalized["data_source"])
    df_tf = _align_timeframe(df_1m, normalized["data_source"]["timeframe"])

    created_at = _format_ts(df_1m["ts"].iloc[0].to_pydatetime())

    engine_config = EngineConfig(
        strategy_id=normalized["strategy"]["id"],
        strategy_params=normalized["strategy"].get("params", {}),
        symbol=normalized["data_source"]["symbol"],
        timeframe=normalized["data_source"]["timeframe"],
        risk_level=normalized["risk"]["level"],
        commission_bps=normalized["costs"]["commission_bps"],
        slippage_bps=normalized["costs"]["slippage_bps"],
        initial_equity=INITIAL_EQUITY,
    )

    try:
        engine_result = run_engine(df_tf, engine_config)
    except ValueError as exc:
        raise RunBuilderError("RUN_CONFIG_INVALID", str(exc), 400)

    for decision in engine_result.decisions:
        decision["run_id"] = run_id

    status_history = ["CREATED", "VALIDATED", "RUNNING", "COMPLETED"]

    config_payload = _build_config_payload(run_id, normalized)
    metrics_payload = _build_metrics_payload(engine_result, engine_config)

    manifest = _build_manifest(
        run_id=run_id,
        owner_user_id=owner_user_id,
        created_at=created_at,
        inputs=normalized,
        inputs_hash=inputs_hash,
        status="COMPLETED",
        status_history=status_history,
        data_meta=data_meta,
        meta=meta,
    )

    temp_dir = runs_root / f".tmp_{run_id}_{uuid.uuid4().hex[:8]}"
    try:
        _write_artifacts(
            temp_dir,
            manifest,
            config_payload,
            metrics_payload,
            engine_result,
            df_1m,
            df_tf,
        )
        _atomic_rename(temp_dir, run_dir)
        _register_run(owner_root, run_dir, manifest)
    except NonFiniteNumberError as exc:
        _cleanup_temp_dir(temp_dir)
        raise RunBuilderError("DATA_INVALID", "Non-finite numeric value", 400) from exc
    except RunBuilderError:
        _cleanup_temp_dir(temp_dir)
        raise
    except Exception as exc:
        _cleanup_temp_dir(temp_dir)
        raise RunBuilderError("RUN_WRITE_FAILED", str(exc), 500) from exc

    return 201, _success_response(run_id, "COMPLETED", inputs_hash)


def _resolve_runs_root() -> Path:
    runs_root = get_runs_root()
    if runs_root is None:
        raise RunBuilderError(
            "RUNS_ROOT_UNSET",
            "RUNS_ROOT is not set",
            503,
            {"env": RUNS_ROOT_ENV},
        )
    if not runs_root.exists():
        raise RunBuilderError(
            "RUNS_ROOT_MISSING",
            "RUNS_ROOT does not exist",
            503,
            {"path": str(runs_root)},
        )
    if not runs_root.is_dir():
        raise RunBuilderError(
            "RUNS_ROOT_INVALID",
            "RUNS_ROOT is not a directory",
            503,
            {"path": str(runs_root)},
        )
    writable, error = _check_runs_root_writable(runs_root)
    if not writable:
        raise RunBuilderError(
            "RUNS_ROOT_NOT_WRITABLE",
            "RUNS_ROOT is not writable",
            503,
            {"path": str(runs_root), "error": error or "permission denied"},
        )
    return runs_root


def _resolve_owner_user_id(user_id: str | None) -> str:
    candidate = (user_id or "").strip()
    if not candidate:
        candidate = (os.getenv("BUFF_DEFAULT_USER") or "").strip()
    if not candidate:
        raise RunBuilderError("USER_MISSING", "X-Buff-User header is required", 400)
    try:
        return validate_user_id(candidate)
    except ValueError as exc:
        raise RunBuilderError(
            "USER_INVALID", "Invalid user id", 400, {"user_id": candidate}
        ) from exc


def _check_runs_root_writable(runs_root: Path) -> tuple[bool, str | None]:
    probe = runs_root / f".buff_write_check_{os.getpid()}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return False, str(exc)
    return True, None


def _normalize_request(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise RunBuilderError("RUN_CONFIG_INVALID", "schema_version is required", 400)

    data_source = payload.get("data_source")
    if not isinstance(data_source, dict):
        raise RunBuilderError("RUN_CONFIG_INVALID", "data_source is required", 400)

    source_type = str(data_source.get("type") or "").lower()
    if source_type != "csv":
        raise RunBuilderError("RUN_CONFIG_INVALID", "data_source.type must be csv", 400)

    path_raw = str(data_source.get("path") or "").strip()
    if not path_raw:
        raise RunBuilderError("RUN_CONFIG_INVALID", "data_source.path is required", 400)

    normalized_path, source_path = _resolve_source_path(path_raw)
    if not source_path.exists():
        raise RunBuilderError(
            "DATA_SOURCE_NOT_FOUND",
            "CSV path not found",
            400,
            {"path": path_raw},
        )

    symbol = str(data_source.get("symbol") or payload.get("symbol") or "").strip().upper()
    if not symbol or not symbol.isalnum():
        raise RunBuilderError("RUN_CONFIG_INVALID", "symbol is invalid", 400)

    timeframe = str(data_source.get("timeframe") or payload.get("timeframe") or "").strip()
    if timeframe not in {"1m", "5m"}:
        raise RunBuilderError("RUN_CONFIG_INVALID", "timeframe must be 1m or 5m", 400)

    start_ts = data_source.get("start_ts")
    end_ts = data_source.get("end_ts")
    if start_ts is not None and end_ts is not None:
        if _parse_ts(start_ts) >= _parse_ts(end_ts):
            raise RunBuilderError("RUN_CONFIG_INVALID", "start_ts must be < end_ts", 400)

    strategy = payload.get("strategy")
    if not isinstance(strategy, dict):
        raise RunBuilderError("RUN_CONFIG_INVALID", "strategy is required", 400)

    strategy_id = str(strategy.get("id") or "").strip()
    if not strategy_id:
        raise RunBuilderError("STRATEGY_INVALID", "strategy.id is required", 400)
    if strategy_id not in {"hold", "ma_cross", "demo_threshold"}:
        raise RunBuilderError("STRATEGY_INVALID", "strategy.id is invalid", 400)

    params = strategy.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise RunBuilderError("STRATEGY_INVALID", "strategy.params must be an object", 400)

    params = {str(key): value for key, value in params.items()}
    if strategy_id == "ma_cross":
        try:
            fast = int(params.get("fast_period", 10))
            slow = int(params.get("slow_period", 20))
        except (TypeError, ValueError) as exc:
            raise RunBuilderError("STRATEGY_INVALID", "ma_cross params invalid", 400) from exc
        if fast <= 0 or slow <= 0 or fast >= slow:
            raise RunBuilderError("STRATEGY_INVALID", "ma_cross params invalid", 400)
        params = {"fast_period": fast, "slow_period": slow}
    elif strategy_id == "demo_threshold":
        try:
            threshold = float(params.get("threshold", 0.0))
        except (TypeError, ValueError) as exc:
            raise RunBuilderError("STRATEGY_INVALID", "demo_threshold params invalid", 400) from exc
        if threshold < 0 or threshold > 10:
            raise RunBuilderError("STRATEGY_INVALID", "demo_threshold params invalid", 400)
        params = {"threshold": threshold}
    else:
        params = {}

    risk = payload.get("risk")
    if not isinstance(risk, dict):
        raise RunBuilderError("RISK_INVALID", "risk is required", 400)
    level = risk.get("level")
    try:
        level_int = int(level)
    except (TypeError, ValueError):
        raise RunBuilderError("RISK_INVALID", "risk.level must be an integer", 400)
    if level_int < 1 or level_int > 5:
        raise RunBuilderError("RISK_INVALID", "risk.level must be 1..5", 400)

    costs = payload.get("costs")
    if not isinstance(costs, dict):
        raise RunBuilderError("RUN_CONFIG_INVALID", "costs is required", 400)
    if "commission_bps" not in costs or "slippage_bps" not in costs:
        raise RunBuilderError("RUN_CONFIG_INVALID", "costs fields are required", 400)
    commission_raw = costs.get("commission_bps")
    slippage_raw = costs.get("slippage_bps")
    if isinstance(commission_raw, bool) or isinstance(slippage_raw, bool):
        raise RunBuilderError("RUN_CONFIG_INVALID", "costs values must be numeric", 400)
    try:
        commission_bps = float(commission_raw)
        slippage_bps = float(slippage_raw)
    except (TypeError, ValueError) as exc:
        raise RunBuilderError("RUN_CONFIG_INVALID", "costs values must be numeric", 400) from exc
    if commission_bps < 0 or slippage_bps < 0:
        raise RunBuilderError("RUN_CONFIG_INVALID", "costs values must be >= 0", 400)

    seed = payload.get("seed", 0)
    try:
        seed_val = int(seed)
    except (TypeError, ValueError):
        seed_val = 0

    normalized = {
        "schema_version": schema_version,
        "data_source": {
            "type": "csv",
            "path": normalized_path,
            "symbol": symbol,
            "timeframe": timeframe,
        },
        "strategy": {
            "id": strategy_id,
            "params": params,
        },
        "risk": {"level": level_int},
        "costs": {"commission_bps": commission_bps, "slippage_bps": slippage_bps},
        "seed": seed_val,
    }

    if start_ts is not None:
        normalized["data_source"]["start_ts"] = _format_ts(_parse_ts(start_ts))
    if end_ts is not None:
        normalized["data_source"]["end_ts"] = _format_ts(_parse_ts(end_ts))

    meta = {}
    for key in ("name", "notes", "created_by"):
        value = payload.get(key)
        if value:
            meta[key] = str(value)

    return _strip_none(normalized), meta


def _is_absolute_path(value: str) -> bool:
    if value.startswith("~"):
        return True
    path = Path(value)
    if path.is_absolute():
        return True
    drive, _ = os.path.splitdrive(value)
    return bool(drive)


def _contains_parent_segments(value: str) -> bool:
    return ".." in Path(value).parts


def _resolve_symlink_target(path: Path) -> Path:
    try:
        target = Path(os.readlink(path))
    except OSError:
        return path.resolve(strict=False)
    if not target.is_absolute():
        target = path.parent / target
    return target.resolve(strict=False)


def _ensure_no_symlink_escape(repo_root: Path, rel_path: Path) -> None:
    current = repo_root
    for part in rel_path.parts:
        current = current / part
        if current.is_symlink():
            target = _resolve_symlink_target(current)
            if not is_within_root(target, repo_root):
                raise RunBuilderError(
                    "RUN_CONFIG_INVALID",
                    "data_source.path must not resolve outside repo",
                    400,
                )


def _resolve_source_path(path_raw: str) -> tuple[str, Path]:
    if _is_absolute_path(path_raw):
        raise RunBuilderError("RUN_CONFIG_INVALID", "data_source.path must be relative", 400)

    normalized = _normalize_rel_path(path_raw)
    if _contains_parent_segments(normalized):
        raise RunBuilderError(
            "RUN_CONFIG_INVALID",
            "data_source.path must not contain '..'",
            400,
        )

    repo_root = Path.cwd().resolve()
    _ensure_no_symlink_escape(repo_root, Path(normalized))
    source_path = (repo_root / Path(normalized)).resolve(strict=False)
    if not is_within_root(source_path, repo_root):
        raise RunBuilderError("RUN_CONFIG_INVALID", "data_source.path must be within repo", 400)
    return normalized, source_path


def _normalize_rel_path(value: str) -> str:
    posix = Path(value).as_posix()
    if posix.startswith("./"):
        posix = posix[2:]
    return posix


def _strip_none(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, dict):
            nested = _strip_none(value)
            cleaned[key] = nested
        else:
            cleaned[key] = value
    return cleaned


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    else:
        text = str(value).strip()
        if text.isdigit():
            dt = datetime.fromtimestamp(int(text) / 1000.0, tz=timezone.utc)
        else:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(text)
            except ValueError as exc:
                raise RunBuilderError("DATA_INVALID", "timestamp invalid", 400) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_ts(value: datetime) -> str:
    dt = value.astimezone(timezone.utc)
    text = dt.isoformat(timespec="milliseconds")
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text


def _load_and_validate_csv(data_source: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = str(data_source["path"])
    normalized_path, source_path = _resolve_source_path(path)
    if not source_path.exists():
        raise RunBuilderError(
            "DATA_SOURCE_NOT_FOUND",
            "CSV path not found",
            400,
            {"path": path},
        )
    try:
        df = pd.read_csv(source_path)
    except Exception as exc:
        raise RunBuilderError("DATA_INVALID", f"Failed to read CSV: {exc}", 400) from exc

    if df.empty:
        raise RunBuilderError("DATA_INVALID", "CSV has no rows", 400)

    cols = {str(col).lower(): col for col in df.columns}
    ts_col = cols.get("timestamp") or cols.get("ts")
    if ts_col is None:
        raise RunBuilderError("DATA_INVALID", "timestamp column missing", 400)

    rename_map = {ts_col: "timestamp"}
    for key in ("open", "high", "low", "close", "volume"):
        if key not in cols:
            raise RunBuilderError("DATA_INVALID", f"Missing required column: {key}", 400)
        rename_map[cols[key]] = key

    df = df.rename(columns=rename_map)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]

    ts_series = df["timestamp"]
    if ts_series.dtype.kind in {"i", "u", "f"}:
        ts_parsed = pd.to_datetime(ts_series, unit="ms", utc=True, errors="coerce")
    else:
        text_series = ts_series.astype(str)
        if text_series.str.match(r"^\d+$").all():
            ts_parsed = pd.to_datetime(text_series.astype("int64"), unit="ms", utc=True)
        else:
            ts_parsed = pd.to_datetime(text_series, utc=True, errors="coerce")

    if ts_parsed.isna().any():
        raise RunBuilderError("DATA_INVALID", "timestamp parse failed", 400)

    try:
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype("float64")
    except (TypeError, ValueError) as exc:
        raise RunBuilderError("DATA_INVALID", "price/volume must be numeric", 400) from exc

    if (df["volume"] < 0).any():
        raise RunBuilderError("DATA_INVALID", "volume must be non-negative", 400)

    df_out = pd.DataFrame(
        {
            "ts": ts_parsed,
            "open": df["open"],
            "high": df["high"],
            "low": df["low"],
            "close": df["close"],
            "volume": df["volume"],
        }
    )

    start_ts = data_source.get("start_ts")
    end_ts = data_source.get("end_ts")
    if start_ts is not None:
        start_dt = _parse_ts(start_ts)
        df_out = df_out[df_out["ts"] >= start_dt]
    if end_ts is not None:
        end_dt = _parse_ts(end_ts)
        df_out = df_out[df_out["ts"] <= end_dt]

    if df_out.empty:
        raise RunBuilderError("DATA_INVALID", "No data after applying time window", 400)

    df_out = df_out.reset_index(drop=True)

    if not df_out["ts"].is_monotonic_increasing:
        raise RunBuilderError("DATA_INVALID", "timestamp must be strictly increasing", 400)

    if df_out["ts"].duplicated().any():
        raise RunBuilderError("DATA_INVALID", "timestamp must be strictly increasing", 400)

    if (df_out["ts"].dt.second != 0).any() or (df_out["ts"].dt.microsecond != 0).any():
        raise RunBuilderError("DATA_INVALID", "timestamp must align to minute", 400)

    diffs = df_out["ts"].diff().dropna()
    if not diffs.eq(pd.Timedelta(minutes=1)).all():
        raise RunBuilderError("DATA_INVALID", "input data must be 1m with no gaps", 400)

    return df_out, {
        "source_path": normalized_path,
        "start_ts": _format_ts(df_out["ts"].iloc[0].to_pydatetime()),
        "end_ts": _format_ts(df_out["ts"].iloc[-1].to_pydatetime()),
    }


def _align_timeframe(df_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe == "1m":
        return df_1m.copy()
    try:
        result = resample_ohlcv(df_1m, timeframe)
    except Exception as exc:
        raise RunBuilderError("DATA_INVALID", f"resample failed: {exc}", 400) from exc
    if result.df.empty:
        raise RunBuilderError("DATA_INVALID", "resample produced no rows", 400)
    return result.df


def _build_timeline(created_at: str, statuses: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for idx, status in enumerate(statuses):
        events.append(
            {
                "timestamp": created_at,
                "type": "run",
                "title": status,
                "detail": f"status={status}",
                "severity": "INFO",
                "stage": status,
                "duration_ms": 0,
                "seq": idx,
            }
        )
    return events


def _build_config_payload(run_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": inputs.get("schema_version"),
        "run_id": run_id,
        "engine_version": ENGINE_VERSION,
        "builder_version": BUILDER_VERSION,
        "inputs": inputs,
    }


def _build_metrics_payload(result, engine_config: EngineConfig) -> dict[str, Any]:
    payload = dict(result.metrics)
    payload["num_trades"] = len(result.trades)
    payload["symbol"] = engine_config.symbol
    payload["timeframe"] = engine_config.timeframe
    payload["strategy_id"] = engine_config.strategy_id
    payload["costs"] = {
        "commission_bps": float(engine_config.commission_bps),
        "slippage_bps": float(engine_config.slippage_bps),
    }
    payload["risk_level"] = int(engine_config.risk_level)
    return payload


def _build_manifest(
    *,
    run_id: str,
    owner_user_id: str,
    created_at: str,
    inputs: dict[str, Any],
    inputs_hash: str,
    status: str,
    status_history: list[str],
    data_meta: dict[str, Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    data_source = inputs["data_source"]
    strategy = inputs["strategy"]
    manifest = {
        "schema_version": inputs.get("schema_version"),
        "run_id": run_id,
        "created_at": created_at,
        "engine_version": ENGINE_VERSION,
        "builder_version": BUILDER_VERSION,
        "status": status,
        "status_history": status_history,
        "inputs": inputs,
        "inputs_hash": inputs_hash,
        "data": {
            "source_type": "csv",
            "source_path": data_meta.get("source_path"),
            "symbol": data_source.get("symbol"),
            "timeframe": data_source.get("timeframe"),
            "start_ts": data_source.get("start_ts"),
            "end_ts": data_source.get("end_ts"),
            "canonical_timeframe": "1m",
            "data_start_ts": data_meta.get("start_ts"),
            "data_end_ts": data_meta.get("end_ts"),
        },
        "strategy": {
            "id": strategy.get("id"),
            "params": strategy.get("params", {}),
        },
        "risk": {"level": inputs["risk"]["level"]},
        "artifacts": {
            "decision_records": "decision_records.jsonl",
            "metrics": "metrics.json",
            "timeline": "timeline.json",
            "additional": [
                "config.json",
                "equity_curve.json",
                "trades.jsonl",
                "ohlcv_1m.jsonl",
                f"ohlcv_{data_source.get('timeframe')}.jsonl",
            ],
        },
    }
    meta_payload: dict[str, Any] = {}
    if meta:
        meta_payload.update(meta)
    meta_payload["owner_user_id"] = owner_user_id
    manifest["meta"] = meta_payload
    return manifest


def _write_artifacts(
    run_dir: Path,
    manifest: dict[str, Any],
    config_payload: dict[str, Any],
    metrics_payload: dict[str, Any],
    engine_result,
    df_1m: pd.DataFrame,
    df_tf: pd.DataFrame,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)

    write_canonical_json(run_dir / "manifest.json", manifest)
    write_canonical_json(run_dir / "config.json", config_payload)
    write_canonical_json(run_dir / "metrics.json", metrics_payload)
    write_canonical_json(run_dir / "equity_curve.json", engine_result.equity_curve)
    write_canonical_json(
        run_dir / "timeline.json",
        _build_timeline(
            manifest["created_at"], manifest.get("status_history", [manifest["status"]])
        ),
    )
    write_canonical_jsonl(run_dir / "decision_records.jsonl", engine_result.decisions)
    write_canonical_jsonl(run_dir / "trades.jsonl", engine_result.trades)

    write_canonical_jsonl(run_dir / "ohlcv_1m.jsonl", _ohlcv_records(df_1m))
    if df_tf is not df_1m:
        write_canonical_jsonl(
            run_dir / f"ohlcv_{manifest['data']['timeframe']}.jsonl", _ohlcv_records(df_tf)
        )
    else:
        write_canonical_jsonl(
            run_dir / f"ohlcv_{manifest['data']['timeframe']}.jsonl", _ohlcv_records(df_1m)
        )


def _ohlcv_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in df.itertuples(index=False):
        records.append(
            {
                "ts": _format_ts(row.ts),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
        )
    return records


def _atomic_rename(src: Path, dst: Path) -> None:
    dst_parent = dst.parent
    dst_parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(src, dst)
    except OSError as exc:
        raise RunBuilderError("RUN_WRITE_FAILED", str(exc), 500) from exc


def _register_run(user_root_path: Path, run_dir: Path, manifest: dict[str, Any]) -> None:
    lock = lock_registry(user_root_path)
    try:
        with lock:
            upsert_registry_entry(user_root_path, run_dir, manifest)
    except TimeoutError as exc:
        _safe_remove_run(run_dir)
        raise RunBuilderError("REGISTRY_LOCK_TIMEOUT", "Registry lock timeout", 503) from exc
    except Exception as exc:
        _safe_remove_run(run_dir)
        raise RunBuilderError("REGISTRY_WRITE_FAILED", "Registry write failed", 500) from exc


def _ensure_registry_entry(user_root_path: Path, run_dir: Path, manifest: dict[str, Any]) -> None:
    try:
        lock = lock_registry(user_root_path)
        with lock:
            upsert_registry_entry(user_root_path, run_dir, manifest)
    except TimeoutError as exc:
        raise RunBuilderError("REGISTRY_LOCK_TIMEOUT", "Registry lock timeout", 503) from exc
    except Exception as exc:
        raise RunBuilderError("REGISTRY_WRITE_FAILED", "Registry write failed", 500) from exc


def _safe_remove_run(run_dir: Path) -> None:
    try:
        if run_dir.exists():
            shutil.rmtree(run_dir)
    except OSError:
        pass


def _cleanup_temp_dir(temp_dir: Path) -> None:
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


def _success_response(run_id: str, status: str, inputs_hash: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": status,
        "inputs_hash": inputs_hash,
        "message": "run ready",
        "links": {
            "self": f"/api/v1/runs/{run_id}",
            "ui": f"/runs/{run_id}",
        },
    }
