from __future__ import annotations

import copy
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import to_canonical_bytes, write_canonical_json
from .experiment_contract import ExperimentContractError, normalize_experiment_request
from .paths import (
    RUNS_ROOT_ENV,
    get_runs_root,
    is_within_root,
    user_experiments_root,
    user_runs_root,
    validate_user_id,
)
from .registry import compute_inputs_hash
from .run_builder import RunBuilderError, create_run
from .runs_root_probe import check_runs_root_writable

_EXECUTION_MODE = "SIM_ONLY"
_CAPABILITIES = ["SIMULATION", "DATA_READONLY"]
_EXPERIMENT_STATUS = {"COMPLETED", "PARTIAL", "FAILED"}


@dataclass
class ExperimentBuilderError(Exception):
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


def create_experiment(
    payload: dict[str, Any], *, user_id: str | None = None
) -> tuple[int, dict[str, Any]]:
    owner_user_id = _resolve_owner_user_id(user_id)
    base_runs_root = _resolve_runs_root()

    runs_root = user_runs_root(base_runs_root, owner_user_id)
    experiments_root = user_experiments_root(base_runs_root, owner_user_id)
    try:
        runs_root.mkdir(parents=True, exist_ok=True)
        experiments_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExperimentBuilderError(
            "RUNS_ROOT_NOT_WRITABLE",
            "RUNS_ROOT is not writable",
            503,
            {"path": str(base_runs_root), "error": str(exc)},
        ) from exc

    writable, error = check_runs_root_writable(runs_root)
    if not writable:
        raise ExperimentBuilderError(
            "RUNS_ROOT_NOT_WRITABLE",
            "RUNS_ROOT is not writable",
            503,
            {"path": str(base_runs_root), "error": error or "permission denied"},
        )

    normalized = _normalize_request(payload)
    experiment_digest = compute_inputs_hash(to_canonical_bytes(normalized))
    experiment_id = f"exp_{experiment_digest[:12]}"
    experiment_dir = (experiments_root / experiment_id).resolve()
    if not is_within_root(experiment_dir, experiments_root):
        raise ExperimentBuilderError(
            "EXPERIMENT_ID_INVALID",
            "experiment_id resolved outside experiments root",
            400,
            {"experiment_id": experiment_id},
        )

    existing_manifest = _load_existing_manifest(experiment_dir)
    if existing_manifest is not None:
        existing_digest = str(existing_manifest.get("experiment_digest") or "")
        if existing_digest == experiment_digest:
            status = _normalize_status(existing_manifest.get("status"))
            return 200, _success_response(
                experiment_id=experiment_id,
                experiment_digest=experiment_digest,
                status=status,
                total_candidates=len(normalized["candidates"]),
                succeeded=len(
                    [
                        item
                        for item in existing_manifest.get("candidates", [])
                        if isinstance(item, dict) and item.get("status") == "COMPLETED"
                    ]
                ),
                failed=len(
                    [
                        item
                        for item in existing_manifest.get("candidates", [])
                        if isinstance(item, dict) and item.get("status") == "FAILED"
                    ]
                ),
            )
        raise ExperimentBuilderError(
            "EXPERIMENT_EXISTS",
            "experiment_id already exists",
            409,
            {"experiment_id": experiment_id},
        )

    candidate_results: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(normalized["candidates"]):
        candidate_id = str(candidate.get("candidate_id") or f"cand_{index + 1:03d}")
        run_config = candidate.get("run_config")
        if not isinstance(run_config, dict):
            raise ExperimentBuilderError(
                "EXPERIMENT_CONFIG_INVALID",
                "candidate.run_config must be an object",
                400,
                {"candidate_index": index, "candidate_id": candidate_id},
            )

        result: dict[str, Any] = {
            "candidate_index": index,
            "candidate_id": candidate_id,
            "status": "FAILED",
            "run_id": None,
        }
        label = candidate.get("label")
        if isinstance(label, str) and label.strip():
            result["label"] = label.strip()

        try:
            status_code, run_response = create_run(copy.deepcopy(run_config), user_id=owner_user_id)
            run_id = str(run_response.get("run_id") or "").strip()
            if not run_id:
                raise ExperimentBuilderError(
                    "RUN_WRITE_FAILED",
                    "Run creation returned empty run_id",
                    500,
                    {"candidate_index": index, "candidate_id": candidate_id},
                )
            run_status = _normalize_status(run_response.get("status"))
            metrics_payload = _load_run_metrics(runs_root, run_id)
            comparison_rows.append(
                _build_comparison_row(
                    candidate_id=candidate_id,
                    candidate_index=index,
                    run_id=run_id,
                    run_status=run_status,
                    metrics_payload=metrics_payload,
                )
            )
            result.update(
                {
                    "status": "COMPLETED",
                    "run_id": run_id,
                    "run_status": run_status,
                    "run_status_code": status_code,
                    "inputs_hash": run_response.get("inputs_hash"),
                }
            )
        except (RunBuilderError, ExperimentBuilderError) as exc:
            result["status"] = "FAILED"
            result["error"] = exc.to_payload()
        except Exception:
            result["status"] = "FAILED"
            result["error"] = {
                "code": "INTERNAL",
                "message": "Internal error",
                "details": {"candidate_index": index, "candidate_id": candidate_id},
            }
        candidate_results.append(result)

    succeeded = len([item for item in candidate_results if item.get("status") == "COMPLETED"])
    failed = len(candidate_results) - succeeded
    if failed == 0:
        overall_status = "COMPLETED"
    elif succeeded == 0:
        overall_status = "FAILED"
    else:
        overall_status = "PARTIAL"

    experiment_manifest = _build_manifest(
        owner_user_id=owner_user_id,
        experiment_id=experiment_id,
        experiment_digest=experiment_digest,
        normalized=normalized,
        candidate_results=candidate_results,
        overall_status=overall_status,
        succeeded=succeeded,
        failed=failed,
    )
    comparison_summary = _build_comparison_summary(
        experiment_id=experiment_id,
        experiment_digest=experiment_digest,
        overall_status=overall_status,
        total_candidates=len(candidate_results),
        succeeded=succeeded,
        failed=failed,
        rows=comparison_rows,
    )
    _write_experiment_artifacts(
        experiments_root=experiments_root,
        experiment_dir=experiment_dir,
        experiment_manifest=experiment_manifest,
        comparison_summary=comparison_summary,
    )

    return 201, _success_response(
        experiment_id=experiment_id,
        experiment_digest=experiment_digest,
        status=overall_status,
        total_candidates=len(candidate_results),
        succeeded=succeeded,
        failed=failed,
    )


def _resolve_runs_root() -> Path:
    runs_root = get_runs_root()
    if runs_root is None:
        raise ExperimentBuilderError(
            "RUNS_ROOT_UNSET",
            "RUNS_ROOT is not set",
            503,
            {"env": RUNS_ROOT_ENV},
        )
    if not runs_root.exists():
        raise ExperimentBuilderError(
            "RUNS_ROOT_MISSING",
            "RUNS_ROOT does not exist",
            503,
            {"path": str(runs_root)},
        )
    if not runs_root.is_dir():
        raise ExperimentBuilderError(
            "RUNS_ROOT_INVALID",
            "RUNS_ROOT is not a directory",
            503,
            {"path": str(runs_root)},
        )
    return runs_root


def _resolve_owner_user_id(user_id: str | None) -> str:
    candidate = (user_id or "").strip()
    if not candidate:
        candidate = (os.getenv("BUFF_DEFAULT_USER") or "").strip()
    if not candidate:
        raise ExperimentBuilderError("USER_MISSING", "X-Buff-User header is required", 400)
    try:
        return validate_user_id(candidate)
    except ValueError as exc:
        raise ExperimentBuilderError(
            "USER_INVALID", "Invalid user id", 400, {"user_id": candidate}
        ) from exc


def _normalize_request(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return normalize_experiment_request(payload)
    except ExperimentContractError as exc:
        raise ExperimentBuilderError(exc.code, exc.message, exc.status_code, exc.details) from exc


def _load_existing_manifest(experiment_dir: Path) -> dict[str, Any] | None:
    if not experiment_dir.exists() or not experiment_dir.is_dir():
        return None
    manifest_path = experiment_dir / "experiment_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _load_run_metrics(runs_root: Path, run_id: str) -> dict[str, Any]:
    run_dir = (runs_root / run_id).resolve()
    if not is_within_root(run_dir, runs_root):
        raise ExperimentBuilderError(
            "RUN_ID_INVALID",
            "run_id resolved outside runs root",
            400,
            {"run_id": run_id},
        )
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        raise ExperimentBuilderError(
            "METRICS_MISSING",
            "metrics.json missing",
            500,
            {"run_id": run_id},
        )
    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentBuilderError(
            "METRICS_INVALID",
            "metrics.json invalid",
            500,
            {"run_id": run_id},
        ) from exc
    if not isinstance(payload, dict):
        raise ExperimentBuilderError(
            "METRICS_INVALID",
            "metrics.json must be an object",
            500,
            {"run_id": run_id},
        )
    return payload


def _build_comparison_row(
    *,
    candidate_id: str,
    candidate_index: int,
    run_id: str,
    run_status: str,
    metrics_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_index": candidate_index,
        "candidate_id": candidate_id,
        "run_id": run_id,
        "status": run_status,
        "strategy_id": _as_str(metrics_payload.get("strategy_id")),
        "symbol": _as_str(metrics_payload.get("symbol")),
        "timeframe": _as_str(metrics_payload.get("timeframe")),
        "risk_level": _as_int(metrics_payload.get("risk_level")),
        "total_return": _as_float(metrics_payload.get("total_return")),
        "final_equity": _as_float(metrics_payload.get("final_equity")),
        "max_drawdown": _as_float(metrics_payload.get("max_drawdown")),
        "win_rate": _as_float(metrics_payload.get("win_rate")),
        "num_trades": _as_int(metrics_payload.get("num_trades")),
    }


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_manifest(
    *,
    owner_user_id: str,
    experiment_id: str,
    experiment_digest: str,
    normalized: dict[str, Any],
    candidate_results: list[dict[str, Any]],
    overall_status: str,
    succeeded: int,
    failed: int,
) -> dict[str, Any]:
    return {
        "schema_version": normalized["schema_version"],
        "experiment_id": experiment_id,
        "experiment_digest": experiment_digest,
        "status": overall_status,
        "status_history": ["CREATED", "RUNNING", overall_status],
        "execution_mode": _EXECUTION_MODE,
        "capabilities": list(_CAPABILITIES),
        "inputs": normalized,
        "candidates": candidate_results,
        "summary": {
            "total_candidates": len(candidate_results),
            "succeeded": succeeded,
            "failed": failed,
        },
        "artifacts": {
            "manifest": "experiment_manifest.json",
            "comparison": "comparison_summary.json",
        },
        "meta": {"owner_user_id": owner_user_id},
    }


def _build_comparison_summary(
    *,
    experiment_id: str,
    experiment_digest: str,
    overall_status: str,
    total_candidates: int,
    succeeded: int,
    failed: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    columns = [
        "candidate_index",
        "candidate_id",
        "run_id",
        "status",
        "strategy_id",
        "symbol",
        "timeframe",
        "risk_level",
        "total_return",
        "final_equity",
        "max_drawdown",
        "win_rate",
        "num_trades",
    ]
    return {
        "schema_version": "1.0.0",
        "experiment_id": experiment_id,
        "experiment_digest": experiment_digest,
        "status": overall_status,
        "counts": {
            "total_candidates": total_candidates,
            "succeeded": succeeded,
            "failed": failed,
        },
        "columns": columns,
        "rows": rows,
    }


def _write_experiment_artifacts(
    *,
    experiments_root: Path,
    experiment_dir: Path,
    experiment_manifest: dict[str, Any],
    comparison_summary: dict[str, Any],
) -> None:
    temp_dir = experiments_root / f".tmp_{experiment_dir.name}"
    _cleanup_temp_dir(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        write_canonical_json(temp_dir / "experiment_manifest.json", experiment_manifest)
        write_canonical_json(temp_dir / "comparison_summary.json", comparison_summary)
        os.replace(temp_dir, experiment_dir)
    except OSError as exc:
        _cleanup_temp_dir(temp_dir)
        raise ExperimentBuilderError("RUN_WRITE_FAILED", str(exc), 500) from exc


def _cleanup_temp_dir(temp_dir: Path) -> None:
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


def _normalize_status(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in _EXPERIMENT_STATUS:
        return text
    if not text:
        return "FAILED"
    return text


def _success_response(
    *,
    experiment_id: str,
    experiment_digest: str,
    status: str,
    total_candidates: int,
    succeeded: int,
    failed: int,
) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "experiment_digest": experiment_digest,
        "status": status,
        "counts": {
            "total_candidates": total_candidates,
            "succeeded": succeeded,
            "failed": failed,
        },
        "links": {
            "manifest": f"/api/v1/experiments/{experiment_id}/manifest",
            "comparison": f"/api/v1/experiments/{experiment_id}/comparison",
        },
    }
