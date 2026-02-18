from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import json
import re
import socket
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from .canonical import (
    canonical_json_bytes,
    sha256_hex_bytes,
    sha256_hex_file,
    write_canonical_json,
    write_canonical_jsonl,
)

REQUEST_SCHEMA_VERSION = "s3.simulation_run_request.v1"
RESULT_SCHEMA_VERSION = "s3.simulation_run_result.v1"

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
_RUN_ID_RE = re.compile(r"^sim_[a-f0-9]{16,64}$")
_ENGINE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
_BUILD_SHA_RE = re.compile(r"^[a-f0-9]{7,64}$")

_REQUIRED_REQUEST_FIELDS = {
    "schema_version",
    "tenant_id",
    "artifact_ref",
    "artifact_sha256",
    "dataset_ref",
    "dataset_sha256",
    "config",
    "config_sha256",
    "seed",
    "engine",
}

_REQUIRED_CONFIG_FIELDS = {
    "clock_source",
    "timestamp_format",
    "event_order_key",
    "numeric_encoding",
    "rounding_mode",
    "price_scale",
    "qty_scale",
    "cash_scale",
}

_REQUIRED_RESULT_FIELDS = {
    "schema_version",
    "tenant_id",
    "simulation_run_id",
    "request_digest_sha256",
    "status",
    "engine",
    "fills",
    "metrics",
    "traces",
    "report_refs",
    "digests",
}

_REQUIRED_RESULT_DIGEST_KEYS = {
    "request_sha256",
    "result_sha256",
    "manifest_sha256",
    "event_log_sha256",
    "fills_sha256",
    "metrics_sha256",
    "report_sha256",
}

_FORBIDDEN_EXECUTION_IMPORT_PREFIXES = ("execution",)


class S3RunnerError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"{code}: {message}")

    def to_error_envelope(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
        payload["error"] = dict(payload)
        return payload


def _validate_no_floats(value: Any, path: str = "$") -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message=f"Float values are forbidden by S3 fixed-point policy: {path}",
            details={"path": path},
        )
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise S3RunnerError(
                    code="RUN_CONFIG_INVALID",
                    message=f"Object keys must be strings at {path}",
                    details={"path": path},
                )
            _validate_no_floats(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for idx, child in enumerate(value):
            _validate_no_floats(child, f"{path}[{idx}]")
        return


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message=f"{field} must be a lowercase 64-char sha256 hex",
            details={"field": field},
        )
    return value


def _require_tenant_id(value: Any, field: str = "tenant_id") -> str:
    if not isinstance(value, str) or not _TENANT_RE.fullmatch(value):
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message=f"{field} does not match required format",
            details={"field": field},
        )
    return value


def _require_simulation_run_id(value: Any, field: str = "simulation_run_id") -> str:
    if not isinstance(value, str) or not _RUN_ID_RE.fullmatch(value):
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message=f"{field} does not match required format",
            details={"field": field},
        )
    return value


def _require_safe_ref(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message=f"{field} must be a non-empty string",
            details={"field": field},
        )
    if ".." in value or "\\" in value or Path(value).is_absolute():
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message=f"{field} must be a safe relative reference",
            details={"field": field},
        )
    return value


def _validate_request(request: dict[str, Any]) -> dict[str, Any]:
    _validate_no_floats(request)
    missing = sorted(_REQUIRED_REQUEST_FIELDS - set(request.keys()))
    if missing:
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message=f"Missing request fields: {', '.join(missing)}",
            details={"missing_fields": missing},
        )

    if request["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message=f"schema_version must be {REQUEST_SCHEMA_VERSION}",
            details={"field": "schema_version"},
        )

    tenant_id = _require_tenant_id(request["tenant_id"], "tenant_id")

    artifact_ref = _require_safe_ref(request["artifact_ref"], "artifact_ref")
    artifact_sha256 = _require_sha256(request["artifact_sha256"], "artifact_sha256")
    dataset_ref = _require_safe_ref(request["dataset_ref"], "dataset_ref")
    dataset_sha256 = _require_sha256(request["dataset_sha256"], "dataset_sha256")

    config = request["config"]
    if not isinstance(config, dict):
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="config must be an object",
            details={"field": "config"},
        )
    config_missing = sorted(_REQUIRED_CONFIG_FIELDS - set(config.keys()))
    if config_missing:
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message=f"Missing config fields: {', '.join(config_missing)}",
            details={"missing_config_fields": config_missing},
        )
    if config["clock_source"] != "dataset_event_time":
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="config.clock_source must be dataset_event_time",
            details={"field": "config.clock_source"},
        )
    if config["timestamp_format"] != "epoch_ms":
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="config.timestamp_format must be epoch_ms",
            details={"field": "config.timestamp_format"},
        )
    if config["event_order_key"] != "event_seq":
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="config.event_order_key must be event_seq",
            details={"field": "config.event_order_key"},
        )
    if config["numeric_encoding"] != "fixed_e8_int":
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="config.numeric_encoding must be fixed_e8_int",
            details={"field": "config.numeric_encoding"},
        )
    if config["rounding_mode"] != "half_even":
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="config.rounding_mode must be half_even",
            details={"field": "config.rounding_mode"},
        )
    for field in ("price_scale", "qty_scale", "cash_scale"):
        value = config[field]
        if not isinstance(value, int) or isinstance(value, bool) or value != 8:
            raise S3RunnerError(
                code="RUN_CONFIG_INVALID",
                message=f"config.{field} must be integer 8",
                details={"field": f"config.{field}"},
            )

    config_sha256 = _require_sha256(request["config_sha256"], "config_sha256")
    computed_config_sha = sha256_hex_bytes(canonical_json_bytes(config))
    if config_sha256 != computed_config_sha:
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="config_sha256 does not match canonical config digest",
            details={"field": "config_sha256"},
        )

    seed = request["seed"]
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="seed must be an integer",
            details={"field": "seed"},
        )
    if seed < 0 or seed > 9223372036854775807:
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="seed must be in range 0..9223372036854775807",
            details={"field": "seed"},
        )

    engine = request["engine"]
    if not isinstance(engine, dict):
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="engine must be an object",
            details={"field": "engine"},
        )
    engine_name = engine.get("name")
    if not isinstance(engine_name, str) or not _ENGINE_NAME_RE.fullmatch(engine_name):
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="engine.name does not match required format",
            details={"field": "engine.name"},
        )
    engine_version = engine.get("version")
    if not isinstance(engine_version, str) or engine_version == "latest":
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="engine.version must be pinned and not 'latest'",
            details={"field": "engine.version"},
        )
    if not _SEMVER_RE.fullmatch(engine_version):
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="engine.version must be semver",
            details={"field": "engine.version"},
        )
    build_sha = engine.get("build_sha")
    if build_sha is not None and (
        not isinstance(build_sha, str) or not _BUILD_SHA_RE.fullmatch(build_sha)
    ):
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="engine.build_sha must be 7..64 lowercase hex when provided",
            details={"field": "engine.build_sha"},
        )

    return {
        "schema_version": request["schema_version"],
        "tenant_id": tenant_id,
        "artifact_ref": artifact_ref,
        "artifact_sha256": artifact_sha256,
        "dataset_ref": dataset_ref,
        "dataset_sha256": dataset_sha256,
        "config": config,
        "config_sha256": config_sha256,
        "seed": seed,
        "engine": engine,
    }


def _validate_event_seq(rows: list[dict[str, Any]], label: str) -> None:
    expected = 1
    for row in rows:
        seq = row.get("event_seq")
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise S3RunnerError(
                code="RUN_CONFIG_INVALID",
                message=f"{label} row event_seq must be integer",
                details={"label": label},
            )
        if seq != expected:
            raise S3RunnerError(
                code="RUN_CONFIG_INVALID",
                message=f"{label} event_seq corrupted; expected {expected}, got {seq}",
                details={"label": label, "expected": expected, "actual": seq},
            )
        expected += 1


def _resolve_input_file(request_file: Path, ref: str, field: str) -> Path:
    base_dir = request_file.resolve().parent
    candidate = (base_dir / ref).resolve()
    try:
        candidate.relative_to(base_dir)
    except ValueError as exc:
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message=f"{field} resolved outside request directory",
            details={"field": field, "ref": ref},
        ) from exc

    if not candidate.exists() or not candidate.is_file():
        raise S3RunnerError(
            code="ARTIFACT_NOT_FOUND",
            message=f"{field} target not found",
            details={"field": field, "ref": ref},
        )
    return candidate


def _verify_input_digest(path: Path, expected_sha256: str, field: str, ref: str) -> None:
    actual_sha256 = sha256_hex_file(path)
    if actual_sha256 != expected_sha256:
        raise S3RunnerError(
            code="INPUT_DIGEST_MISMATCH",
            message=f"{field} sha256 does not match input bytes",
            details={
                "field": field,
                "ref": ref,
                "expected": expected_sha256,
                "actual": actual_sha256,
            },
        )


def _simulation_run_id(request: dict[str, Any]) -> str:
    identity_tuple = [
        request["tenant_id"],
        request["artifact_sha256"],
        request["dataset_sha256"],
        request["config_sha256"],
        request["seed"],
        request["engine"]["name"],
        request["engine"]["version"],
    ]
    return f"sim_{sha256_hex_bytes(canonical_json_bytes(identity_tuple))[:16]}"


def _resolve_simulation_run_dir(output_root: Path, tenant_id: str, simulation_run_id: str) -> Path:
    root = output_root.resolve()
    run_dir = (root / tenant_id / "simulations" / simulation_run_id).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise S3RunnerError(
            code="RUN_CONFIG_INVALID",
            message="Resolved simulation path escapes output root",
            details={"field": "simulation_run_id"},
        ) from exc
    return run_dir


def _is_forbidden_execution_module(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in _FORBIDDEN_EXECUTION_IMPORT_PREFIXES
    )


def _assert_no_live_execution_path(source_root: Path | None = None) -> None:
    root = source_root or Path(__file__).resolve().parent
    violations: list[dict[str, Any]] = []

    for source_file in sorted(root.rglob("*.py")):
        source_text = source_file.read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=str(source_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_forbidden_execution_module(alias.name):
                        violations.append(
                            {
                                "file": str(source_file),
                                "line": node.lineno,
                                "module": alias.name,
                            }
                        )
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                if _is_forbidden_execution_module(module_name):
                    violations.append(
                        {
                            "file": str(source_file),
                            "line": node.lineno,
                            "module": module_name,
                        }
                    )

    if violations:
        raise S3RunnerError(
            code="LIVE_EXECUTION_PATH_FORBIDDEN",
            message="S3 runtime must not import execution adapters",
            details={"violations": violations},
        )


def _run_corrupted_error(
    tenant_id: str,
    simulation_run_id: str,
    message: str,
    field: str | None = None,
) -> S3RunnerError:
    details: dict[str, Any] = {
        "tenant_id": tenant_id,
        "simulation_run_id": simulation_run_id,
    }
    if field is not None:
        details["field"] = field
    return S3RunnerError(code="RUN_CORRUPTED", message=message, details=details)


def _network_disabled_error(operation: str) -> S3RunnerError:
    return S3RunnerError(
        code="NETWORK_DISABLED",
        message="Network egress is disabled in S3 simulation runtime",
        details={"operation": operation},
    )


@contextmanager
def _s3_no_network_guard() -> Any:
    def _blocked_create_connection(*args: Any, **kwargs: Any) -> Any:
        raise _network_disabled_error("socket.create_connection")

    def _blocked_getaddrinfo(*args: Any, **kwargs: Any) -> Any:
        raise _network_disabled_error("socket.getaddrinfo")

    def _blocked_socket_connect(*args: Any, **kwargs: Any) -> Any:
        raise _network_disabled_error("socket.connect")

    with (
        patch("socket.create_connection", _blocked_create_connection),
        patch("socket.getaddrinfo", _blocked_getaddrinfo),
        patch.object(socket.socket, "connect", _blocked_socket_connect),
    ):
        yield


def _validate_loaded_result_payload(
    payload: dict[str, Any], tenant_id: str, simulation_run_id: str
) -> dict[str, Any]:
    missing_fields = sorted(_REQUIRED_RESULT_FIELDS - set(payload.keys()))
    if missing_fields:
        raise _run_corrupted_error(
            tenant_id,
            simulation_run_id,
            f"result.json missing fields: {', '.join(missing_fields)}",
            field="result.json",
        )

    if payload["schema_version"] != RESULT_SCHEMA_VERSION:
        raise _run_corrupted_error(
            tenant_id,
            simulation_run_id,
            f"result.json schema_version must be {RESULT_SCHEMA_VERSION}",
            field="schema_version",
        )

    if payload["tenant_id"] != tenant_id:
        raise S3RunnerError(
            code="RUN_NOT_FOUND",
            message="Simulation run not found for tenant",
            details={"tenant_id": tenant_id, "simulation_run_id": simulation_run_id},
        )

    if payload["simulation_run_id"] != simulation_run_id:
        raise _run_corrupted_error(
            tenant_id,
            simulation_run_id,
            "result.json simulation_run_id mismatch",
            field="simulation_run_id",
        )

    digests = payload["digests"]
    if not isinstance(digests, dict):
        raise _run_corrupted_error(
            tenant_id,
            simulation_run_id,
            "result.json digests must be an object",
            field="digests",
        )
    missing_digests = sorted(_REQUIRED_RESULT_DIGEST_KEYS - set(digests.keys()))
    if missing_digests:
        raise _run_corrupted_error(
            tenant_id,
            simulation_run_id,
            f"result.json digests missing keys: {', '.join(missing_digests)}",
            field="digests",
        )
    for key in _REQUIRED_RESULT_DIGEST_KEYS:
        _require_sha256(digests[key], f"digests.{key}")

    expected_result_sha256 = digests["result_sha256"]
    payload_for_hash = json.loads(json.dumps(payload))
    payload_for_hash["digests"]["result_sha256"] = ""
    computed_result_sha256 = sha256_hex_bytes(canonical_json_bytes(payload_for_hash))
    if expected_result_sha256 != computed_result_sha256:
        raise _run_corrupted_error(
            tenant_id,
            simulation_run_id,
            "result.json digest mismatch",
            field="digests.result_sha256",
        )

    return payload


def replay_simulation_result(
    output_root: Path, tenant_id: str, simulation_run_id: str
) -> dict[str, Any]:
    _assert_no_live_execution_path()
    canonical_tenant = _require_tenant_id(tenant_id, "tenant_id")
    canonical_run_id = _require_simulation_run_id(simulation_run_id, "simulation_run_id")
    run_dir = _resolve_simulation_run_dir(output_root, canonical_tenant, canonical_run_id)
    result_path = run_dir / "result.json"

    if not result_path.exists() or not result_path.is_file():
        raise S3RunnerError(
            code="RUN_NOT_FOUND",
            message="Simulation run not found for tenant",
            details={"tenant_id": canonical_tenant, "simulation_run_id": canonical_run_id},
        )

    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _run_corrupted_error(
            canonical_tenant, canonical_run_id, "result.json is invalid JSON", "result.json"
        ) from exc

    if not isinstance(payload, dict):
        raise _run_corrupted_error(
            canonical_tenant,
            canonical_run_id,
            "result.json must contain a JSON object",
            "result.json",
        )

    return _validate_loaded_result_payload(payload, canonical_tenant, canonical_run_id)


def load_simulation_result(
    output_root: Path, tenant_id: str, simulation_run_id: str
) -> dict[str, Any]:
    return replay_simulation_result(output_root, tenant_id, simulation_run_id)


def run_simulation_request(
    request_file: Path,
    output_root: Path,
    simulation_hook: Callable[[], None] | None = None,
) -> Path:
    _assert_no_live_execution_path()
    request_data = json.loads(request_file.read_text(encoding="utf-8"))
    request = _validate_request(request_data)

    artifact_path = _resolve_input_file(request_file, request["artifact_ref"], "artifact_ref")
    dataset_path = _resolve_input_file(request_file, request["dataset_ref"], "dataset_ref")
    _verify_input_digest(
        artifact_path, request["artifact_sha256"], "artifact_sha256", request["artifact_ref"]
    )
    _verify_input_digest(
        dataset_path, request["dataset_sha256"], "dataset_sha256", request["dataset_ref"]
    )

    request_canonical_bytes = canonical_json_bytes(request)
    request_sha256 = sha256_hex_bytes(request_canonical_bytes)
    simulation_run_id = _simulation_run_id(request)

    run_dir = _resolve_simulation_run_dir(output_root, request["tenant_id"], simulation_run_id)

    with _s3_no_network_guard():
        if simulation_hook is not None:
            simulation_hook()

        event_rows: list[dict[str, Any]] = [
            {
                "event_seq": 1,
                "event_type": "SIMULATION_STARTED",
                "seed": request["seed"],
                "simulation_run_id": simulation_run_id,
                "ts_epoch_ms": 0,
            }
        ]
        fills_rows: list[dict[str, Any]] = []
        _validate_event_seq(event_rows, "event_log")
        _validate_event_seq(fills_rows, "fills")

        metrics_values = {
            "perf.net_pnl_e8": 0,
            "risk.max_drawdown_e8": 0,
            "trade.fill_count_i64": 0,
        }

        manifest_payload = {
            "schema_version": "s3.simulation_manifest.v1",
            "simulation_run_id": simulation_run_id,
            "tenant_id": request["tenant_id"],
            "request_digest_sha256": request_sha256,
            "artifacts": {
                "digests": "digests.json",
                "event_log": "event_log.jsonl",
                "fills": "fills.jsonl",
                "metrics": "metrics.json",
                "report": "report_summary.json",
                "result": "result.json",
            },
        }
        metrics_payload = {
            "artifact_ref": "metrics.json",
            "values": metrics_values,
        }
        report_payload = {
            "schema_version": "s3.report_summary.v1",
            "simulation_run_id": simulation_run_id,
            "status": "skeleton",
        }

        run_dir.mkdir(parents=True, exist_ok=True)

        write_canonical_json(run_dir / "manifest.json", manifest_payload)
        write_canonical_jsonl(run_dir / "event_log.jsonl", event_rows)
        write_canonical_jsonl(run_dir / "fills.jsonl", fills_rows)
        write_canonical_json(run_dir / "metrics.json", metrics_payload)
        write_canonical_json(run_dir / "report_summary.json", report_payload)

        manifest_sha256 = sha256_hex_file(run_dir / "manifest.json")
        event_log_sha256 = sha256_hex_file(run_dir / "event_log.jsonl")
        fills_sha256 = sha256_hex_file(run_dir / "fills.jsonl")
        metrics_sha256 = sha256_hex_file(run_dir / "metrics.json")
        report_sha256 = sha256_hex_file(run_dir / "report_summary.json")

        digests_payload = {
            "event_log_sha256": event_log_sha256,
            "fills_sha256": fills_sha256,
            "manifest_sha256": manifest_sha256,
            "metrics_sha256": metrics_sha256,
            "report_sha256": report_sha256,
            "request_sha256": request_sha256,
        }

        result_payload: dict[str, Any] = {
            "digests": {
                **digests_payload,
                # Deterministic preimage placeholder to avoid self-referential hashing cycles.
                "result_sha256": "",
            },
            "engine": request["engine"],
            "fills": {
                "artifact_ref": "fills.jsonl",
                "entries": fills_rows,
                "row_count": 0,
                "sha256": fills_sha256,
            },
            "metrics": {
                "artifact_ref": "metrics.json",
                "sha256": metrics_sha256,
                "values": metrics_values,
            },
            "report_refs": [
                {
                    "artifact_ref": "report_summary.json",
                    "kind": "summary",
                    "sha256": report_sha256,
                }
            ],
            "request_digest_sha256": request_sha256,
            "schema_version": RESULT_SCHEMA_VERSION,
            "simulation_run_id": simulation_run_id,
            "status": "succeeded",
            "tenant_id": request["tenant_id"],
            "traces": {
                "artifact_ref": "event_log.jsonl",
                "event_count": len(event_rows),
                "sha256": event_log_sha256,
            },
        }

        result_sha256 = sha256_hex_bytes(canonical_json_bytes(result_payload))
        result_payload["digests"]["result_sha256"] = result_sha256
        digests_payload["result_sha256"] = result_sha256

        write_canonical_json(run_dir / "result.json", result_payload)
        write_canonical_json(run_dir / "digests.json", digests_payload)

    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic S3 simulation skeleton.")
    parser.add_argument("--request-json", help="Path to SimulationRunRequest JSON file.")
    parser.add_argument(
        "--output-root",
        default="runs",
        help="Base output root.",
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Replay mode: load SimulationRunResult for --tenant-id and --simulation-run-id.",
    )
    parser.add_argument("--tenant-id", help="Tenant identifier for replay mode.")
    parser.add_argument("--simulation-run-id", help="Simulation run identifier for replay mode.")
    args = parser.parse_args(argv)

    output_root = Path(args.output_root).resolve()
    try:
        if args.replay:
            if args.request_json:
                raise S3RunnerError(
                    code="RUN_CONFIG_INVALID",
                    message="--request-json is not allowed with --replay",
                    details={"field": "request_json"},
                )
            if not args.tenant_id:
                raise S3RunnerError(
                    code="RUN_CONFIG_INVALID",
                    message="--tenant-id is required with --replay",
                    details={"field": "tenant_id"},
                )
            if not args.simulation_run_id:
                raise S3RunnerError(
                    code="RUN_CONFIG_INVALID",
                    message="--simulation-run-id is required with --replay",
                    details={"field": "simulation_run_id"},
                )
            result = replay_simulation_result(
                output_root, tenant_id=args.tenant_id, simulation_run_id=args.simulation_run_id
            )
            print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            return 0

        if not args.request_json:
            raise S3RunnerError(
                code="RUN_CONFIG_INVALID",
                message="--request-json is required unless --replay is set",
                details={"field": "request_json"},
            )

        request_path = Path(args.request_json).resolve()
        run_dir = run_simulation_request(request_path, output_root)
    except S3RunnerError as exc:
        print(json.dumps(exc.to_error_envelope(), sort_keys=True, separators=(",", ":")))
        return 1
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
