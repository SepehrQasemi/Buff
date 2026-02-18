from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s3.canonical import canonical_json_bytes, sha256_hex_bytes
from s3.runner import S3RunnerError, load_simulation_result, run_simulation_request


def _build_request(request_path: Path, tenant_id: str) -> None:
    artifact_bytes = b"artifact-bytes-v1"
    dataset_bytes = b"dataset-bytes-v1"
    (request_path.parent / "artifact.bin").write_bytes(artifact_bytes)
    (request_path.parent / "dataset.bin").write_bytes(dataset_bytes)

    config = {
        "cash_scale": 8,
        "clock_source": "dataset_event_time",
        "event_order_key": "event_seq",
        "numeric_encoding": "fixed_e8_int",
        "price_scale": 8,
        "qty_scale": 8,
        "rounding_mode": "half_even",
        "timestamp_format": "epoch_ms",
    }
    request = {
        "artifact_ref": "artifact.bin",
        "artifact_sha256": sha256_hex_bytes(artifact_bytes),
        "config": config,
        "config_sha256": sha256_hex_bytes(canonical_json_bytes(config)),
        "dataset_ref": "dataset.bin",
        "dataset_sha256": sha256_hex_bytes(dataset_bytes),
        "engine": {"name": "buff-sim", "version": "1.0.0"},
        "schema_version": "s3.simulation_run_request.v1",
        "seed": 42,
        "tenant_id": tenant_id,
    }
    request_path.write_text(json.dumps(request, sort_keys=True), encoding="utf-8")


def test_s3_cross_tenant_isolation(tmp_path: Path) -> None:
    request_dir = tmp_path / "request"
    request_dir.mkdir(parents=True, exist_ok=True)
    request_path = request_dir / "request.json"
    _build_request(request_path, tenant_id="alice")

    runs_root = tmp_path / "runs"
    run_dir = run_simulation_request(request_path, runs_root)
    simulation_run_id = run_dir.name

    result = load_simulation_result(
        runs_root, tenant_id="alice", simulation_run_id=simulation_run_id
    )
    assert result["tenant_id"] == "alice"
    assert result["simulation_run_id"] == simulation_run_id

    with pytest.raises(S3RunnerError) as exc_info:
        load_simulation_result(runs_root, tenant_id="bob", simulation_run_id=simulation_run_id)
    err = exc_info.value
    assert err.code == "RUN_NOT_FOUND"
    assert err.details["tenant_id"] == "bob"
