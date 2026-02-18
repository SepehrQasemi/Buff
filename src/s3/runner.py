from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

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


def _validate_no_floats(value: Any, path: str = "$") -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        raise ValueError(f"Float values are forbidden by S3 fixed-point policy: {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"Object keys must be strings at {path}")
            _validate_no_floats(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for idx, child in enumerate(value):
            _validate_no_floats(child, f"{path}[{idx}]")
        return


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase 64-char sha256 hex")
    return value


def _require_safe_ref(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    if ".." in value or "\\" in value or Path(value).is_absolute():
        raise ValueError(f"{field} must be a safe relative reference")
    return value


def _validate_request(request: dict[str, Any]) -> dict[str, Any]:
    _validate_no_floats(request)
    missing = sorted(_REQUIRED_REQUEST_FIELDS - set(request.keys()))
    if missing:
        raise ValueError(f"Missing request fields: {', '.join(missing)}")

    if request["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {REQUEST_SCHEMA_VERSION}")

    tenant_id = request["tenant_id"]
    if not isinstance(tenant_id, str) or not _TENANT_RE.fullmatch(tenant_id):
        raise ValueError("tenant_id does not match required format")

    artifact_ref = _require_safe_ref(request["artifact_ref"], "artifact_ref")
    artifact_sha256 = _require_sha256(request["artifact_sha256"], "artifact_sha256")
    dataset_ref = _require_safe_ref(request["dataset_ref"], "dataset_ref")
    dataset_sha256 = _require_sha256(request["dataset_sha256"], "dataset_sha256")

    config = request["config"]
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    config_missing = sorted(_REQUIRED_CONFIG_FIELDS - set(config.keys()))
    if config_missing:
        raise ValueError(f"Missing config fields: {', '.join(config_missing)}")
    if config["clock_source"] != "dataset_event_time":
        raise ValueError("config.clock_source must be dataset_event_time")
    if config["timestamp_format"] != "epoch_ms":
        raise ValueError("config.timestamp_format must be epoch_ms")
    if config["event_order_key"] != "event_seq":
        raise ValueError("config.event_order_key must be event_seq")
    if config["numeric_encoding"] != "fixed_e8_int":
        raise ValueError("config.numeric_encoding must be fixed_e8_int")
    if config["rounding_mode"] != "half_even":
        raise ValueError("config.rounding_mode must be half_even")
    for field in ("price_scale", "qty_scale", "cash_scale"):
        value = config[field]
        if not isinstance(value, int) or isinstance(value, bool) or value != 8:
            raise ValueError(f"config.{field} must be integer 8")

    config_sha256 = _require_sha256(request["config_sha256"], "config_sha256")
    computed_config_sha = sha256_hex_bytes(canonical_json_bytes(config))
    if config_sha256 != computed_config_sha:
        raise ValueError("config_sha256 does not match canonical config digest")

    seed = request["seed"]
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")
    if seed < 0 or seed > 9223372036854775807:
        raise ValueError("seed must be in range 0..9223372036854775807")

    engine = request["engine"]
    if not isinstance(engine, dict):
        raise ValueError("engine must be an object")
    engine_name = engine.get("name")
    if not isinstance(engine_name, str) or not _ENGINE_NAME_RE.fullmatch(engine_name):
        raise ValueError("engine.name does not match required format")
    engine_version = engine.get("version")
    if not isinstance(engine_version, str) or engine_version == "latest":
        raise ValueError("engine.version must be pinned and not 'latest'")
    if not _SEMVER_RE.fullmatch(engine_version):
        raise ValueError("engine.version must be semver")
    build_sha = engine.get("build_sha")
    if build_sha is not None and (
        not isinstance(build_sha, str) or not _BUILD_SHA_RE.fullmatch(build_sha)
    ):
        raise ValueError("engine.build_sha must be 7..64 lowercase hex when provided")

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
            raise ValueError(f"{label} row event_seq must be integer")
        if seq != expected:
            raise ValueError(f"{label} event_seq corrupted; expected {expected}, got {seq}")
        expected += 1


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


def run_simulation_request(request_file: Path, output_root: Path) -> Path:
    request_data = json.loads(request_file.read_text(encoding="utf-8"))
    request = _validate_request(request_data)

    request_canonical_bytes = canonical_json_bytes(request)
    request_sha256 = sha256_hex_bytes(request_canonical_bytes)
    simulation_run_id = _simulation_run_id(request)

    run_dir = output_root / request["tenant_id"] / "simulations" / simulation_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

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
    parser.add_argument(
        "--request-json", required=True, help="Path to SimulationRunRequest JSON file."
    )
    parser.add_argument(
        "--output-root",
        default="runs",
        help="Base output root. Runner writes to <output-root>/<tenant>/simulations/<run_id>/",
    )
    args = parser.parse_args(argv)

    request_path = Path(args.request_json).resolve()
    output_root = Path(args.output_root).resolve()
    run_dir = run_simulation_request(request_path, output_root)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
